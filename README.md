# Job Scheduling

Pipeline de otimização de sequenciamento de produção usando o modelo **Time-Index** (Pyomo + HiGHS).

## Estrutura do pipeline

```
data_input_process.py  →  optimize.py  →  data_output_process.py  →  dashboard.py
      input.json              output.json          result.parquet / .csv       Gantt
```

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
python src/main/optimize.py
```

O caminho de entrada/saída está fixo no bloco `__main__` do arquivo. Edite `data_input_path` e `data_output_path` antes de rodar.

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

Saída: `data/trusted/<DDMMYYYY>/<status>/demanda/result_<data>.parquet` e `.csv`

---

### 4. Dashboard

Requer que o passo 3 tenha sido executado (usa o parquet gerado).

```bash
streamlit run src/main/dashboard.py -- \
  --dt 2025-10-13 \
  --trusted-root data/trusted \
  --model-config-dir data/model_config
```

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
