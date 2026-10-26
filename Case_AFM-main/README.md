# Solução Base dos Operadores (Case AFM)

Este diretório contém a implementação da **Solução Base (Baseline)** que reproduz a regra prática de sequenciamento utilizada pelos operadores no chão de fábrica, parametrizada com o mesmo horizonte ($H$), turnos, tempos de setup e função objetivo da **Heurística ILS/VNS** (`src/heuristics/`) e do **Modelo Exato MIP** (`src/main/optimize.py`).

---

## 1. Como os Operadores Realizam o Sequenciamento

O algoritmo de simulação da operação manual ([`schedule_machine_baseline`](file:///home/leandrobandeira/Documents/me/tcc/TCC-Machine-Scheduling/Case_AFM-main/main.py#L549-L697) em [`main.py`](file:///home/leandrobandeira/Documents/me/tcc/TCC-Machine-Scheduling/Case_AFM-main/main.py)) segue quatro etapas:

### 1.1. Ordenação Fixa pela Prioridade do Operador (`ordenacao`)
- Na demanda bruta (`demanda/*.parquet`), cada ordem de produção possui a coluna `ordenacao`, preenchida manualmente pelo PCP/operadores para indicar a sequência planejada de execução na máquina.
- Os jobs válidos (`Status_Processed == ""`) atribuídos a uma máquina são ordenados em ordem crescente de `(ordenacao, job_id)` (registros sem `ordenacao` recebem o valor padrão `100`).
- Diferentemente da heurística e do MIP, **a sequência não é reordenada** para antecipar jobs liberados mais cedo ou reduzir setups/atrasos: o operador segue estritamente a fila definida por `ordenacao`.

### 1.2. Discretização do Tempo e Horizonte Semanal ($H$)
- O tempo é discretizado em slots de **5 minutos** (`time_step = 5`, `288` slots por dia).
- O horizonte compreende os **dias úteis (segunda a sexta-feira) da mesma semana** a partir de `day_start` (`00:00` da data do lote).
- Em cada dia útil, os slots válidos de início (`start_slots`) são formados pelos turnos ativos da máquina em [`brut_shifts.csv`](file:///home/leandrobandeira/Documents/me/tcc/TCC-Machine-Scheduling/Case_AFM-main/model_config/brut_shifts.csv) (descontando intervalos de refeição e trocas de turno) e limitados pelo teto diário `max_dia` de [`brut_recurso_time_capacity.csv`](file:///home/leandrobandeira/Documents/me/tcc/TCC-Machine-Scheduling/Case_AFM-main/model_config/brut_recurso_time_capacity.csv):
  $$\text{cap}_{\text{dia}} = \min\left(\text{último slot do turno no dia},\; \text{start\_slot\_day} + \left\lfloor \frac{\text{max\_dia}}{5} \right\rfloor\right)$$
- O horizonte máximo da máquina é $H = \text{start\_slots}[-1]$ e a abertura do primeiro turno é $\text{first\_slot} = \text{start\_slots}[0]$.

### 1.3. Alocação Sequencial nos Slots de Abertura (`next_start_slots`)
Para cada job $j$ na ordem definida por `ordenacao`:
1. O tempo de processamento em minutos é calculado considerando a eficiência (OEE) da máquina e convertido em slots:
   $$p_j = \left\lceil \frac{\text{qtd\_moldes}_j \times \text{tempo\_ciclo}_j / \text{OEE}}{5} \right\rceil$$
2. Para cada sub-máquina paralela $m \in \{0, \dots, M-1\}$ (onde $M = \text{job\_capacity}$ de [`brut_machine_information.csv`](file:///home/leandrobandeira/Documents/me/tcc/TCC-Machine-Scheduling/Case_AFM-main/model_config/brut_machine_information.csv)), calcula-se o instante mais cedo em que o job $j$ pode iniciar após o último job $i$ daquela sub-máquina:
   $$\text{earliest}_m = \max\big(\text{last\_completion}_m + s_{i,j},\; r_j,\; \text{first\_slot},\; \text{bloqueio\_recurso}_m\big)$$
3. O início efetivo é ajustado (*snapped*) para o primeiro slot de turno válido disponível a partir de $\text{earliest}_m$:
   $$\text{start}_m = \text{next\_start\_slots}[\text{earliest}_m]$$
4. O job é alocado na sub-máquina $m^*$ que proporciona o **menor `start`**.
   - Se $\text{start}_{m^*} \le H$, o job é agendado no intervalo $[\text{start}_{m^*},\; \text{start}_{m^*} + p_j)$.
   - Se $\text{start}_{m^*} > H$, o job **não cabe no horizonte semanal** e é marcado como não alocado (`start = -1`, `end = -1`, `sub_machine = M`).

---

## 2. O Que é Feito com o Recurso (Caixa de Macho / Ferramental)

Cada job requer uma ferramenta física específica — a **caixa de macho** identificada por `_kf_macho` (mapeada para um índice denso `resource_id` $\in \{0, \dots, R-1\}$). O tratamento do recurso atua em duas frentes:

### 2.1. Tempo de Setup entre Jobs Consecutivos na Mesma Sub-Máquina
O tempo de preparação ($s_{i,j}$) entre o job anterior $i$ e o job atual $j$ na mesma sub-máquina segue [`get_setup_minutes_and_slots`](file:///home/leandrobandeira/Documents/me/tcc/TCC-Machine-Scheduling/Case_AFM-main/main.py#L462-L494):
1. **Primeiro job da sub-máquina (`i = None`)**: setup zero ($s_{0,j} = 0$).
2. **Mesmo recurso (`_kf_macho_i == _kf_macho_j`)**: como a mesma caixa de macho permanece montada na máquina, **não há setup** ($s_{i,j} = 0$).
3. **Caixas conjugadas (`not_setup` em [`setup.csv`](file:///home/leandrobandeira/Documents/me/tcc/TCC-Machine-Scheduling/Case_AFM-main/model_config/setup.csv))**: caixas cadastradas na mesma linha separadas por `/` (ex.: `385B/386B`, `2706A/2A/3A`) compartilham a mesma montagem física e **não exigem setup entre si** ($s_{i,j} = 0$).
4. **Troca de caixa de macho**: consulta-se a configuração (`A` ou `B`) de cada caixa em [`setup.csv`](file:///home/leandrobandeira/Documents/me/tcc/TCC-Machine-Scheduling/Case_AFM-main/model_config/setup.csv) (com *fallback* para configuração `"A"` nos recursos sem entrada explícita em `setup.csv`, como `carrossel`, `chao`, `cold box pequena` e `cold box 4`) e obtém-se o tempo em [`setup_times.csv`](file:///home/leandrobandeira/Documents/me/tcc/TCC-Machine-Scheduling/Case_AFM-main/model_config/setup_times.csv) convertido em slots:
   $$s_{i,j} = \left\lceil \frac{\text{setup\_time\_min}(\text{config}_i \to \text{config}_j)}{5} \right\rceil$$

### 2.2. Restrição de Não-Simultaneidade e `big_setup` entre Sub-Máquinas Paralelas ($M > 1$)
Em máquinas com múltiplas estações paralelas (como `pepset_chao` com $M = 2$ e `pepset_carrossel` com $M = 10$):
- Como existe apenas uma unidade física de cada caixa de macho (`_kf_macho`), **duas sub-máquinas diferentes não podem utilizar o mesmo `resource_id` ao mesmo tempo**.
- Além disso, para transferir uma caixa de macho de uma sub-máquina $k$ para outra sub-máquina $m \ne k$, exige-se o tempo de **`big_setup` = 5 horas (60 slots)**.
- Assim, sempre que um job usando o recurso $r$ é alocado na sub-máquina $k$ no intervalo $[\text{start}, \text{end})$, ele bloqueia o recurso $r$ para qualquer **outra** sub-máquina $m \ne k$ durante a janela:
  $$\big[\text{start},\; \min(H + 1,\; \text{end} + \text{big\_setup})\big)$$
  - Na **mesma** sub-máquina $k$, um job subsequente com o mesmo recurso $r$ pode iniciar imediatamente em $\text{end}$ (com setup $0$).
  - Em **outra** sub-máquina $m \ne k$, um job com o recurso $r$ só pode iniciar a partir de $\text{end} + \text{big\_setup}$.

---

## 3. Função Objetivo e Formato de Saída

Para permitir comparação direta com a heurística, [`schedule_machine_baseline`](file:///home/leandrobandeira/Documents/me/tcc/TCC-Machine-Scheduling/Case_AFM-main/main.py#L549-L697) avalia a solução gerada usando a mesma função objetivo hierárquica de [`objective.cpp`](file:///home/leandrobandeira/Documents/me/tcc/TCC-Machine-Scheduling/src/heuristics/utils/objective.cpp):

$$\text{FO} = \sum_{j \in \text{Alocados}} \max(0,\; \text{end}_j - d_j) + \epsilon \sum_{j \in \text{Alocados}} \text{end}_j + |\text{NãoAlocados}| \cdot W_{\text{unalloc}} + V_{\text{recurso}} \cdot W_{\text{viol}}$$

onde:
- $W_{\text{unalloc}} = N \cdot H + 1$
- $\epsilon = \dfrac{1}{W_{\text{unalloc}}}$
- $W_{\text{viol}} = N \cdot W_{\text{unalloc}} + 1$

O resultado de cada instância é salvo em `output_baseline.json` seguindo exatamente o esquema de `output_heuristic.json`.

---

## 4. Como Executar

### 4.1. Gerar o Baseline para um Lote Específico
```bash
python3 Case_AFM-main/main.py \
  --base-data data/raw/01122025/94 \
  --model-config-dir Case_AFM-main/model_config
```

### 4.2. Comparar Baseline vs Heurística (`run_config.json`)
O script [`compare_heuristic.py`](file:///home/leandrobandeira/Documents/me/tcc/TCC-Machine-Scheduling/Case_AFM-main/compare_heuristic.py) lê as instâncias de [`run_config.json`](file:///home/leandrobandeira/Documents/me/tcc/TCC-Machine-Scheduling/run_config.json), **recalcula sempre um novo baseline** (`output_baseline.json`), **preserva os resultados existentes da heurística** (`output_heuristic.json`) e gera [`Case_AFM-main/baseline_vs_heuristic.csv`](file:///home/leandrobandeira/Documents/me/tcc/TCC-Machine-Scheduling/Case_AFM-main/baseline_vs_heuristic.csv):

```bash
# Comparar todas as instâncias que já possuem output_heuristic.json
python3 Case_AFM-main/compare_heuristic.py --only-existing-heuristic

# Comparar todas as instâncias do run_config.json (executando a heurística apenas onde ainda não existir output_heuristic.json)
python3 Case_AFM-main/compare_heuristic.py
```
