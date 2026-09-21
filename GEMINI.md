# GEMINI.md - Diretrizes do Projeto TCC-Machine-Scheduling

Este arquivo fornece contexto, diretrizes de arquitetura, comandos frequentes e regras de desenvolvimento para o assistente de IA no repositório **TCC-Machine-Scheduling**.

---

## 1. Visão Geral do Projeto

Pipeline de otimização de sequenciamento de produção (*Job Scheduling*) em máquinas paralelas com duas abordagens complementares:
1. **Otimização Exata (Pyomo + HiGHS / Gurobi)**: Modelo *Time-Index* minimizando *tardiness* (atraso acumulado) com desempate por *completion time*.
2. **Heurística ILS (Iterated Local Search em C++17)**: Resolução rápida com construtivo GRASP e busca local VNS (Swap, OrOpt-1/2/3, 2-Opt) em múltiplas rotas/máquinas paralelas.

---

## 2. Estrutura do Repositório

```
models/                   ← Documentação dos modelos de otimização
└── model.md              ← Formulação matemática MIP Time-Index completa
src/
├── main/                 ← Pipeline de otimização exata em Python
│   ├── entities.py       ← Dataclasses (Job, Machine)
│   ├── data_input_process.py  ← Leitura de dados brutos e geração do input.json
│   ├── optimize.py       ← Modelo Pyomo (Time-Index) + Solver (HiGHS / Gurobi)
│   ├── data_output_process.py ← Pós-processamento e geração de Parquet/CSV
│   └── download_demanda.py   ← Integração de download de dados
├── analysis/             ← Ferramentas de análise e visualização
│   ├── dashboard.py      ← Interface Streamlit (Gantt, setups, indisponibilidades)
│   ├── instances_data.py ← Gerador de matriz de instâncias e run_config.json
│   ├── results_data.py   ← Consolidador de resultados
│   └── compare_heuristic.py ← Comparativo entre exato vs heurística
└── heuristics/           ← Heurística ILS implementada em C++17
    ├── main.cpp
    ├── Makefile          ← Compilação da heurística executável
    ├── algorithms/       ← Lógica de ILS e LocalSearch (VNS)
    ├── models/           ← Data structures (Job, Solution, ProblemData)
    └── utils/            ← Leitura de JSON, cálculo de FO e utilitários
tests/                    ← Testes automatizados (pytest)
├── test_output.py        ← Validações do output do otimizador (cobertura, sobreposição, etc.)
run.sh                    ← Script Bash orquestrador do pipeline completo
run_config.json           ← Configuração das instâncias ativas a processar
requirements.txt          ← Dependências Python
```

---

## 3. Comandos Frequentes

### Configuração do Ambiente Python
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Executar o Pipeline Completo
```bash
./run.sh                  # Processa todas as instâncias definidas em run_config.json
./run.sh --skip-existing  # Pula instâncias que já possuem output.json gerado
```

### Executar Testes Automatizados
```bash
pytest
pytest tests/test_output.py
```

### Compilar e Executar a Heurística em C++
```bash
cd src/heuristics
make                      # Gera o executável ./heuristic
./heuristic <caminho_input.json>
```

### Executar o Dashboard de Análise (Streamlit)
```bash
streamlit run src/analysis/dashboard.py
```

### Atualizar Instâncias e Resultados
```bash
python3 -m src.analysis.instances_data  # Varre data/raw/ e atualiza run_config.json
python3 -m src.analysis.results_data    # Consolida resultados em data/results.csv
```

---

## 4. Regras e Boas Práticas de Código

1. **Preservação do Modelo de Otimização (`src/main/optimize.py`)**:
   - Respeitar a função objetivo: Minimizar tardiness total, com critério secundário de minimização de completion time para desempate.
   - Restrições críticas: não sobreposição de jobs por máquina, tempos de setup entre famílias/produtos, datas de liberação (*release date / not_before_date*), prazos de entrega (*due date*), indisponibilidades e restrições de recursos compartilhados.

2. **Garantia de Qualidade e Validação**:
   - Sempre execute `pytest` após realizar alterações na lógica de pré/pós-processamento ou no otimizador.
   - Assegurar que nenhum job seja ignorado ou duplicado durante a conversão `data_input_process` -> `optimize` -> `data_output_process`.

3. **Manutenção do Código C++ (`src/heuristics/`)**:
   - Padrão **C++17**.
   - Garantir compatibilidade entre os dados lidos de `input.json` no Python e a estrutura `ProblemData.hpp` no C++.
   - Sempre validar a compilação com `make` no diretório `src/heuristics/`.

4. **Tratamento de Dados (`data/`)**:
   - `data/raw/`: Arquivos de entrada brutos (não alterar diretamente).
   - `data/trusted/`: Arquivos intermediários e resultados por instância (`input.json`, `output.json`, `result.parquet`).
   - `data/latest/`: Resultados consolidados mais recentes organizados por status.

5. **Comunicação e Estilo de Código**:
   - Manter código legível, fortemente tipado (Type Hints em Python) e bem documentado em português ou inglês segundo o padrão existente no projeto.
