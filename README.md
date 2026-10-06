# Job Scheduling

Pipeline de otimização de sequenciamento de produção (*Job Scheduling*) em máquinas paralelas com duas abordagens complementares:
1. **Otimização Exata (Pyomo + HiGHS / Gurobi)**: Modelo *Time-Index* minimizando *total tardiness* com desempate por *completion time*.
2. **Heurística ILS (Iterated Local Search em C++17)**: Resolução rápida com construtivo GRASP e busca local RVND (7 vizinhanças intra e inter-rota) para instâncias paralelas.

---

## 1. Estrutura do Projeto

```
src/
├── main/                 ← Pipeline de otimização exata
│   ├── entities.py       ← Dataclasses (Job, Machine)
│   ├── data_input_process.py  ← Leitura de dados brutos e geração do input.json
│   ├── optimize.py       ← Modelo Pyomo (Time-Index) + Solver (HiGHS / Gurobi) + Warm Start
│   └── data_output_process.py ← Pós-processamento e geração de Parquet/CSV
├── analysis/             ← Ferramentas de análise e visualização
│   ├── dashboard.py      ← Interface Streamlit (Gantt, setups, indisponibilidades)
│   ├── instances_data.py ← Gerador de matriz de instâncias e run_config.json
│   ├── results_data.py   ← Consolidador de resultados dos exatos (data/results.csv)
│   └── compare_heuristic.py ← Comparativo MIP vs Heurística (data/heuristic_vs_mip.csv)
└── heuristics/           ← Meta-heurística ILS implementada em C++17
    ├── main.cpp          ← Ponto de entrada da heurística C++
    ├── Makefile          ← Compilação do executável com rastreamento de .hpp
    ├── algorithms/       ← Algoritmos ILS e Busca Local RVND
    ├── models/           ← Estruturas de dados (Job, Solution, ProblemData)
    └── utils/            ← Leitura/Escrita de JSON (output_heuristic.json) e FO
tests/                    ← Testes automatizados (pytest)
├── test_output.py        ← Validações do output do otimizador (cobertura, sobreposição, etc.)
run.sh                    ← Script Bash orquestrador do pipeline completo
run_config.json           ← Configuração das instâncias ativas a processar
requirements.txt          ← Dependências Python
```

---

## 2. Função de Cada Arquivo

| Arquivo / Módulo | Descrição / Função |
|---|---|
| `src/main/entities.py` | Data classes `Job` e `Machine` fortemente tipadas usadas pelo otimizador. |
| `src/main/data_input_process.py` | Lê demanda em `data/raw/`, valida jobs, calcula slots de tempo, setups e janelas, gerando `input.json` em `data/trusted/`. |
| `src/main/optimize.py` | Lê `input.json`, constrói o modelo MIP Time-Index em Pyomo, suporta solver HiGHS ou Gurobi, inicialização via *Warm Start* e gera `output.json`. |
| `src/main/data_output_process.py` | Lê `input.json` + `output.json`, converte slots para datetime e escreve `result.parquet`/`.csv` em `data/trusted/` e `data/latest/`. |
| `src/analysis/dashboard.py` | Dashboard Streamlit interativo para análise de Gantt semanal/diário, setups, indisponibilidades e gargalos. |
| `src/analysis/instances_data.py` | Varre `data/raw/`, executa o pré-processamento para cada data e gera `data/instances.csv` e `run_config.json`. |
| `src/analysis/results_data.py` | Consolida todos os `output.json` do otimizador MIP em `data/results.csv`. |
| `src/analysis/compare_heuristic.py` | Executa/Lê o `output_heuristic.json` da heurística e compara lado a lado com o `output.json` (MIP), gerando `data/heuristic_vs_mip.csv`. |
| `src/heuristics/main.cpp` | Ponto de entrada C++ da heurística ILS. Recebe `<input.json> <machine_id>` e salva `output_heuristic.json`. |
| `src/heuristics/algorithms/ils.hpp/.cpp` | Loop ILS com construtivo GRASP (RCL) e perturbação adaptativa (intra/inter rota). |
| `src/heuristics/algorithms/LocalSearch.hpp/.cpp` | Busca local RVND explorando 7 vizinhanças (Swap, OrOpt-1/2/3, 2-Opt, SwapInter, Realocate). |
| `src/heuristics/models/ProblemData.hpp` | Agrega dados estáticos da máquina (jobs, matriz de setup, slots, H, penalidade de recurso). |
| `src/heuristics/models/solution.hpp` | Estrutura de dados da solução (vetores de rotas por sub-máquina, caches e bitsets de recursos). |
| `src/heuristics/utils/read_instance.hpp/.cpp` | Parser do `input.json` e gerador do arquivo `output_heuristic.json`. |
| `src/heuristics/utils/objective.hpp/.cpp` | Função de avaliação da FO total e verificação de restrições de recurso compartilhados via bitsets. |
| `src/heuristics/utils/params.hpp` | Parâmetros globais (`EPS_FO = 1e-7`, `writeDebugFiles`). |
| `src/heuristics/Makefile` | Compilador C++17 com flags `-O3 -march=native` e rastreamento de `.hpp`. |
| `run.sh` | Bash script orquestrador dos 3 passos do pipeline exato. |
| `tests/test_output.py` | Suite de testes automatizados `pytest` para validação de integridade dos planos. |

---

## 3. Orquestrador do Pipeline (`run.sh`)

Executa o fluxo completo (`data_input_process` → `optimize` → `data_output_process`) para as instâncias ativas em `run_config.json`.

```bash
./run.sh [opções]
```

### Flags do `run.sh`:

| Flag | Valor Padrão | Descrição |
|---|---|---|
| `--skip-existing` | `false` | Pula a otimização em datas que já possuem `output.json` gerado. |
| `--use-gurobi` | `false` | Executa o `optimize.py` utilizando o solver **Gurobi** em vez do HiGHS. |
| `--use-warm-start` | `false` | Passa a flag `--use-warm-start` para o `optimize.py` inicializar as variáveis binárias com o `output_heuristic.json`. |

---

## 4. Bateria de Scripts Python e Suas Flags

### A. Otimizador MIP (`src/main/optimize.py`)

Constrói e resolve o modelo matematicamente exato (Time-Index).

```bash
python3 src/main/optimize.py --dt YYYY-MM-DD [opções]
```

| Flag | Tipo / Padrão | Descrição |
|---|---|---|
| `--dt` | `str` (Obrigatório) | Data da instância no formato `YYYY-MM-DD`. |
| `--trusted-root` | `Path` (`data/trusted`) | Diretório raiz das instâncias processadas. |
| `--only-status` | `str...` (`None`) | Lista de status/lotes específicos a otimizar (ex: `--only-status 59 60`). |
| `--only-machines` | `str...` (`None`) | Lista de nomes de máquinas a otimizar (ex: `--only-machines pepset_vibrado`). |
| `--use-gurobi` | `bool` (`False`) | Usa o Gurobi Solver em vez do HiGHS. |
| `--use-warm-start` | `bool` (`False`) | Carrega a solução em `output_heuristic.json` para inicializar as variáveis binárias ($x_{j,t,m}$) no Pyomo (*MIP Start*). |

---

### B. Pré-Processamento de Entrada (`src/main/data_input_process.py`)

Transforma arquivos Parquet de demanda bruta em `input.json`.

```bash
python3 src/main/data_input_process.py --dt YYYY-MM-DD [opções]
```

| Flag | Tipo / Padrão | Descrição |
|---|---|---|
| `--dt` | `str` (Obrigatório) | Data no formato `YYYY-MM-DD`. |
| `--day-start` | `str` (`<dt> 00:00`) | Horário inicial do horizonte de planejamento. |
| `--time-step` | `int` (`5`) | Tamanho do slot em minutos. |
| `--raw-root` | `Path` (`data/raw`) | Diretório dos arquivos brutos. |
| `--trusted-root` | `Path` (`data/trusted`) | Diretório de destino dos arquivos `input.json`. |
| `--model-config-dir` | `Path` (`data/raw/model_config`) | Diretório dos arquivos de parâmetro e setups. |
| `--only-status` | `str...` (`None`) | Filtrar por lotes específicos. |

---

### C. Pós-Processamento de Saída (`src/main/data_output_process.py`)

Converte os resultados numéricos dos slots em horários e gera arquivos Parquet/CSV.

```bash
python3 src/main/data_output_process.py --dt YYYY-MM-DD [opções]
```

| Flag | Tipo / Padrão | Descrição |
|---|---|---|
| `--dt` | `str` (Obrigatório) | Data no formato `YYYY-MM-DD`. |
| `--trusted-root` | `Path` (`data/trusted`) | Diretório raiz das instâncias. |
| `--only-status` | `str...` (`None`) | Filtrar por lotes específicos. |

---

### D. Comparador de Resultados (`src/analysis/compare_heuristic.py`)

Gera o arquivo `data/heuristic_vs_mip.csv` comparando a solução exata com a heurística.

```bash
python3 -m src.analysis.compare_heuristic [opções]
```

| Flag | Tipo / Padrão | Descrição |
|---|---|---|
| `--skip-existing` | `bool` (`False`) | Reaproveita os arquivos `output_heuristic.json` existentes sem re-executar o binário C++. |

---

## 5. Execução da Heurística C++ (`src/heuristics/`)

Implementação em C++17 do **ILS (Iterated Local Search)** com busca local **RVND (Random Variable Neighborhood Descent)**.

### Compilação:

```bash
cd src/heuristics
make clean && make
```
Gera o binário executável `src/heuristics/heuristic`.

### Execução Direta:

```bash
./heuristic <caminho/input.json> <machine_id>
```

**Exemplo:**
```bash
./heuristic ../../data/trusted/05112025/60/input.json 2
```

**Saída:**
* Imprime o tempo de resolução, as rotas por sub-máquina e a Função Objetivo no terminal.
* Salva automaticamente o arquivo `output_heuristic.json` no mesmo diretório do `input.json` fornecido.

---

## 6. Dashboard Interativo (Streamlit)

Visualização de Gantt, setups e diagnósticos a partir dos resultados em `data/latest/`.

```bash
streamlit run src/analysis/dashboard.py
```

---

## 7. Testes Automatizados (`pytest`)

Executa as validações de integridade dos planos (cobertura de jobs, setups, não sobreposição e restrições de recurso):

```bash
pytest tests/test_output.py -v
```
