# Job Scheduling

Pipeline de otimização de sequenciamento de produção usando o modelo **Time-Index** (Pyomo + HiGHS) e heurística **ILS** (Iterated Local Search).

## Estrutura do projeto

```
src/
  main/           ← pipeline de otimização exata
    entities.py
    data_input_process.py
    optimize.py
    data_output_process.py
  analysis/       ← ferramentas de análise e visualização
    dashboard.py
    instances_data.py
    results_data.py
  heuristics/     ← heurística ILS em C++
    main.cpp
    algorithms/
      ils.hpp / ils.cpp
    models/
      job.hpp
      solution.hpp
      ProblemData.hpp
    utils/
      read_instance.hpp / read_instance.cpp
    Makefile
tests/
  test_output.py
run.sh            ← orquestrador do pipeline completo
run_config.json   ← instâncias a processar (gerado por instances_data.py)
```

## Função de cada arquivo

| Arquivo | Função |
|---|---|
| `src/main/entities.py` | Data classes `Job` e `Machine` usadas pelo otimizador |
| `src/main/data_input_process.py` | Lê demanda de `data/raw/`, valida jobs, calcula slots de tempo e setups, gera `input.json` em `data/trusted/` |
| `src/main/optimize.py` | Lê `input.json`, constrói e resolve o modelo Time-Index (Pyomo + HiGHS) minimizando soma de tardiness com desempate por completion time, gera `output.json` |
| `src/main/data_output_process.py` | Lê `input.json` + `output.json`, converte slots para datetime, escreve `result.parquet`/`.csv` em `data/trusted/` e `data/latest/` |
| `src/analysis/dashboard.py` | Dashboard Streamlit interativo: Gantt semanal e por dia, setups, indisponibilidades e delays por dia (não por hora) |
| `src/analysis/instances_data.py` | Varre `data/raw/`, executa `data_input_process.py` para cada data, limpa todos os `output.json` e `data/latest/` existentes, gera `data/instances.csv` e `run_config.json` filtrado por `INSTANCE_FILTERS` |
| `src/analysis/results_data.py` | Coleta todos os `output.json` em `data/trusted/`, cruza com `input.json` e gera `data/results.csv` consolidado |
| `tests/test_output.py` | Valida o output do otimizador: cobertura de jobs, sem sobreposição, respeitado not_before_date, setup times e resource constraint |
| `src/heuristics/algorithms/ils.hpp/.cpp` | Método construtivo GRASP e função de avaliação da solução (sum tardiness + penalidade + ε·sum completion time), respeitando start_slots da máquina |
| `src/heuristics/models/job.hpp` | Struct `Job` com id, processing_slots, release_date_slot, due_date_slot, resource_id e idx |
| `src/heuristics/models/solution.hpp` | Struct `Solution` com sequência de jobs e valor da função objetivo |
| `src/heuristics/models/ProblemData.hpp` | Agrega jobs, setup_matrix, start_slots, H (último slot) e first_slot por instância de máquina |
| `src/heuristics/utils/read_instance.hpp/.cpp` | Lê `input.json` e constrói `ProblemData` (jobs, setup_matrix, H, first_slot, start_slots) |
| `src/heuristics/Makefile` | Compila o executável `heuristic` em C++17 |

## Estrutura do pipeline

```
data_input_process.py  →  optimize.py  →  data_output_process.py
      input.json              output.json       result.parquet / .csv
                                                data/latest/<status>/
```

---

## Executar o pipeline completo (`run.sh`)

Orquestra os 3 passos do pipeline para todas as instâncias definidas em `run_config.json`.

```bash
./run.sh
```

Por padrão roda todas as instâncias, mesmo que já tenham `output.json`. Para pular instâncias que já foram otimizadas:

```bash
./run.sh --skip-existing
```

| Flag | Padrão | Descrição |
|---|---|---|
| `--skip-existing` | `false` | Pula datas onde todos os status já têm `output.json` |

O `run_config.json` é gerado por `instances_data.py` e define quais datas, status e máquinas processar.

---

## Heurística ILS (`src/heuristics/`)

Implementação em C++17 de uma heurística construtiva GRASP para o problema de sequenciamento.

### Compilar

```bash
cd src/heuristics
make
```

Gera o executável `src/heuristics/heuristic`.

### Executar

```bash
./heuristic <caminho/input.json> <machine_id>
```

Exemplo:

```bash
./heuristic ../../data/trusted/01122025/94/input.json 5
```

Imprime a sequência construída e o valor da função objetivo.

### Função objetivo (heurística)

Mesma estrutura do modelo exato:

```
FO = sum_tardiness + W * jobs_não_alocados + ε * sum_completion_time
W   = (n_jobs * H) + 1
ε   = 1 / W
H   = último start_slot da máquina
```

Jobs são considerados não alocados quando o primeiro slot válido disponível excede `H`. A busca do slot usa `lower_bound` sobre `start_slots`, respeitando gaps de turno da máquina.

---

## Testes

Os testes em `tests/test_output.py` validam automaticamente os resultados do otimizador para os pares `(data, status)` definidos em `run_config.json`.

### Executar todos os testes

```bash
pytest tests/test_output.py -v -s
```

### Executar com logs visíveis

```bash
# Mostrar INFO e acima
pytest tests/test_output.py -v -s --log-cli-level=INFO

# Mostrar apenas WARNING e acima
pytest tests/test_output.py -v -s --log-cli-level=WARNING
```

### Limitar o número de pares testados

```bash
MAX_PAIRS=2 pytest tests/test_output.py -v -s
```

### O que é validado

| Teste | Validação |
|---|---|
| `test_all_jobs_present` | Nenhum `job_id` no output sem correspondência no input |
| `test_only_start` | Jobs agendados têm `inicio` preenchido |
| `test_not_before_date` | Nenhum job inicia antes do `not_before_date` |
| `test_no_overlap_same_submachine` | Sem sobreposição na mesma `(maquina, sub_machine)` |
| `test_parallel_jobs` | `sub_machine` máxima < `job_capacity` da máquina |
| `test_setup_times` | Gap entre jobs consecutivos >= tempo de setup do `input.json` |
| `test_resource_constraint` | Jobs com mesmo `resource_id` em sub-máquinas diferentes têm gap >= `big_setup` |

---

## Como executar

### 1. Preparação do input

Lê a demanda de `data/raw/<DDMMYYYY>/<status>/demanda/*.parquet`, valida os jobs e gera o `input.json`.

```bash
python src/main/data_input_process.py \
  --dt 2025-10-13 \
  --raw-root data/raw \
  --trusted-root data/trusted \
  --model-config-dir data/raw/model_config
```

Argumentos opcionais:

| Argumento | Padrão | Descrição |
|---|---|---|
| `--day-start` | `<dt> 00:00` | Início do horizonte de planejamento |
| `--time-step` | `5` | Tamanho do slot em minutos |
| `--only-status` | todos | Processar apenas lotes específicos (ex: `34 35`) |

Saída: `data/trusted/<DDMMYYYY>/<status>/input.json`

---

### 2. Otimização

Lê o `input.json`, resolve um modelo Time-Index por máquina e gera o `output.json`.

```bash
python src/main/optimize.py \
  --dt 2025-10-13
```

Argumentos opcionais:

| Argumento | Padrão | Descrição |
|---|---|---|
| `--trusted-root` | `data/trusted` | Diretório raiz das instâncias |
| `--only-status` | todos | Processar apenas lotes específicos (ex: `34 35`) |

Saída: `data/trusted/<DDMMYYYY>/<status>/output.json`

---

### 3. Pós-processamento

Lê `input.json` + `output.json` e gera os arquivos de resultado.

```bash
python src/main/data_output_process.py \
  --dt 2025-10-13 \
  --trusted-root data/trusted
```

Argumento opcional `--only-status` funciona igual ao passo 1.

Saídas:
- `data/trusted/<DDMMYYYY>/<status>/demanda/result_<data>.parquet` e `.csv` — histórico com data
- `data/latest/<status>/result.parquet`, `result.csv` e `input.json` — sobrescrito a cada execução

---

## Ferramentas de análise (`src/analysis/`)

Ferramentas independentes do otimizador para visualização e exploração dos dados.

### Dashboard

Requer que o passo 3 tenha sido executado. Lê automaticamente de `data/latest/`.

```bash
streamlit run src/analysis/dashboard.py -- \
  --model-config-dir data/raw/model_config
```

Argumentos opcionais:

| Argumento | Padrão | Descrição |
|---|---|---|
| `--latest-dir` | `data/latest` | Diretório com os resultados mais recentes |
| `--model-config-dir` | `data/raw/model_config` | Diretório com os arquivos de parâmetros do modelo |

### Resultados de otimização

Lê todos os `output.json` em `data/trusted/`, cruza com o `input.json` correspondente para obter o nome da máquina e gera um CSV consolidado.

```bash
python src/analysis/results_data.py
```

Saída: `data/results.csv`

| Coluna | Origem | Descrição |
|---|---|---|
| `dt` | nome da pasta `<DDMMYYYY>` | Data da instância (YYYY-MM-DD) |
| `status` | nome da subpasta | Lote processado |
| `machine_name` | `input.json → machines` | Nome da máquina (via `machine_id`) |
| `objective_function` | `output.json` | Valor da função objetivo (sum tardiness + penalidade + ε·sum completion time), arredondado em 5 casas decimais |
| `mip_gap` | `output.json` | Gap relativo MIP `\|incumbent - bound\| / \|incumbent\|`; `null` se sem solução ou ótimo exato (gap=0) |
| `count_jobs_not_allocated` | `output.json` | Jobs não alocados (penalizados) |
| `solve_time_seconds` | `output.json` | Tempo de resolução do solver |
| `count_machines` | `input.json → machines.job_capacity` | Número de sub-máquinas |

---

### Análise de instâncias

Executa `data_input_process.py` para todos os lotes em `data/raw/` e gera um CSV com o tamanho de cada instância por máquina.

```bash
python src/analysis/instances_data.py
```

Saída: `data/instances.csv`

| Coluna | Descrição |
|---|---|
| `date` | Data da instância (YYYY-MM-DD) |
| `status` | Lote processado |
| `machine_id` | ID da máquina |
| `machine_name` | Nome da máquina |
| `job_capacity` | Capacidade de sub-máquinas |
| `count_jobs` | Quantidade de jobs alocados à máquina |

---

## Regras de exclusão de jobs

Jobs marcados com `Status_Processed` não entram na otimização. As marcações acontecem em ordem:

| Condição | `Status_Processed` |
|---|---|
| Algum campo obrigatório nulo (`not_before_date`, `deadline`, `caixa`, `processo`, `recurso`, `qtd_moldes`, `_kf_macho`, `_kf_producao`, `Tempo Total (minutos)`) | `"ERRO dado faltando"` |
| `not_before_date > deadline` | `"Erro Not before date > deadline"` |
| `not_before_date` normalizado > último dia útil do horizonte | `"Erro not before posterior ao ultimo dia"` |

Jobs com `Status_Processed != ""` aparecem no resultado final (parquet) sem `inicio` e `fim` preenchidos, para rastreabilidade.

---

## Ajustes de datas fora do horizonte

### `deadline` anterior ao início do horizonte

Se `deadline < day_start`, o deadline é **avançado para `day_start`** e o job recebe `lateness = 1`:

```
deadline  <  day_start
    └─► deadline = day_start   (slot 0)
    └─► lateness = 1
```

O job não é excluído — ele entra na otimização com deadline no slot 0, sinalizando que já está atrasado.

### `not_before_date` anterior ao início do horizonte

Se `not_before_date < day_start`, o cálculo `(not_before_date - day_start) / time_step` resulta em valor negativo, que é **truncado para 0** via `max(0, ...)`:

```
not_before_date  <  day_start
    └─► release_date_slot = 0   (pode iniciar no primeiro slot disponível)
```

### `not_before_date` posterior ao último dia útil

Job é **excluído** da otimização com `Status_Processed = "Erro not before posterior ao ultimo dia"`. Não faz sentido planejar um job que não pode começar dentro do horizonte.

---

## Parâmetros do modelo (`data/raw/model_config`)

| Arquivo | Conteúdo |
|---|---|
| `brut_machine_information.csv` | Máquinas, recursos, capacidade (`maximo_caixas`), turnos |
| `brut_recurso_time_capacity.csv` | OEE e tempo máximo de uso por dia (`max_dia`) por recurso |
| `brut_shifts.csv` | Horários de turno por dia da semana |
| `setup.csv` | Configuração de machos por recurso |
| `setup_times.csv` | Tempos de setup entre configurações |
