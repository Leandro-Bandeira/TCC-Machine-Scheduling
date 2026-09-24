if (route_idx >= 0 && route_idx < (int)route_caches.size())
            route_caches[route_idx].is_dirty = true;# Arquitetura de Avaliação de Movimentos na Heurística

Este documento descreve o funcionamento detalhado do mecanismo de **avaliação da função objetivo e avaliação incremental de movimentos (Delta Evaluation)** implementado em C++17 ([`src/heuristics/utils/objective.cpp`](file:///home/leandro-bandeira/Documents/me/TCC/TCC-Machine-Scheduling/src/heuristics/utils/objective.cpp), [`objective.hpp`](file:///home/leandro-bandeira/Documents/me/TCC/TCC-Machine-Scheduling/src/heuristics/utils/objective.hpp) e [`src/heuristics/models/solution.hpp`](file:///home/leandro-bandeira/Documents/me/TCC/TCC-Machine-Scheduling/src/heuristics/models/solution.hpp)).

---

## 1. Composição da Função Objetivo (FO)

A função objetivo da heurística reflete estritamente a formulação matemática do modelo exato MIP (*Time-Index*), minimizando o atraso com desempate por tempo de término e penalização severa para inviabilidades:

$$
f(s) = \sum_{j \in \text{Alocados}} T_j + W_{\text{not\_allocated}} \times \sum_{j \in \text{NãoAlocados}} 1 + \epsilon \times \sum_{j \in \text{Alocados}} C_j + \text{Penalidade}_{\text{big\_setup}}
$$

### Componentes:

1. **Total Tardiness ($\sum T_j$)**: Atraso acumulado dos jobs alocados, onde $T_j = \max(0, C_j - d_j)$ ($d_j$ é o *due date* do job).
2. **Penalidade por Não-Alocação ($W_{\text{not\_allocated}} \times \sum 1$)**:
   $$
   W_{\text{not\_allocated}} = (N - 1) \times H + 1
   $$

   onde $N$ é o número total de jobs e $H$ é o horizonte de planejamento. Esse peso garante **dominância estrita**: qualquer solução que deixe de alocar 1 job terá custo superior a qualquer atraso acumulado viável.
3. **Desempate por Completion Time ($\epsilon \times \sum C_j$)**:
   $$
   \epsilon = \frac{1}{W_{\text{not\_allocated}}}
   $$

   Serve como critério secundário para desempatar soluções com mesmo atraso, antecipando o término dos jobs na linha sem interferir na meta primária de tardiness.
4. **Penalidade de Conflito de Recurso Compartilhado ($\text{Penalidade}_{\text{big\_setup}}$)**:
   Jobs com mesmo `resource_id` processados em máquinas distintas devem respeitar uma janela mínima de separação de `big_setup` slots. Caso haja sobreposição entre máquinas paralelas, aplica-se uma penalidade por par violado:
   $$
   \text{Penalidade}_{\text{violação}} = W_{\text{not\_allocated}} \times \text{count\_machines}
   $$

---

## 2. O Motor de Avaliação de uma Rota (`computeRoute`)

A função estática de template `computeRoute` é o núcleo comum compartilhado por todas as rotinas de avaliação:

```cpp
template <typename BitsAccessor>
static double computeRoute(std::vector<Job>& route, const ProblemData& problem_data, 
                           BitsAccessor getBits, std::vector<bool>& seen, 
                           std::vector<int>& touched, bool write_job_fields);
```

### Lógica de Simulação Sequencial:

1. **Sentinelas (Dummies)**: A rota possui o formato `[Dummy_0, Job_1, ..., Job_k, Dummy_0]`. O Dummy inicial tem `idx = 0` e garante que o primeiro job real não pague setup de transição (`setup_matrix[0][job.idx] = 0`).
2. **Setup entre Jobs**: Para cada job $j$ precedido por $i$, obtém-se o tempo de setup na matriz $S_{i, j} = \text{setup\_matrix}[i][j]$.
3. **Instante Mais Cedo de Início (`earliest`)**:
   $$
   \text{earliest} = \max(\text{last\_completion\_time} + S_{i, j}, \; \text{release\_date\_slot}_j, \; \text{first\_slot})
   $$
4. **Alinhamento na Grade de Turnos (`next_start_slots`)**:
   A máquina só pode operar em instantes autorizados pelo calendário de turnos. A tabela pré-computada `next_start_slots[earliest]` retorna o primeiro slot válido $\ge \text{earliest}$ em $\mathcal{O}(1)$.
5. **Checagem de Horizonte ($H$)**:
   * Se $\text{start} > H$: o job não cabe no turno/horizonte. Não é processado e incrementa o contador de não-alocados.
   * Se $\text{start} \le H$: calcula-se $\text{end} = \text{start} + p_j$, atualiza-se $C_j$, $T_j$ e $\text{last\_completion\_time} = \text{end}$.
6. **Marcação de Conflito de Recursos em Bitset**:
   Se a instância possui mais de uma máquina (`count_machines > 1`), ativa-se o intervalo de ocupação estendida do recurso no bitset correspondente:
   $$
   [\text{start}, \; \min(H + 1, \text{end} + \text{big\_setup}))
   $$
7. **Flag `write_job_fields`**:
   * `true` em `evaluate()`: grava permanentemente `job.start` e `job.end`.
   * `false` nas funções de busca local: apenas simula os valores para calcular a FO, sem alterar os jobs reais.

---

## 3. Estrutura de Caching e Bitsets em `Solution`

Para permitir a exploração de milhares de vizinhos por segundo no RVND sem recalcular rotas inalteradas:

```
Solution
 ├── routes[m]                   -> Sequência de jobs por máquina (inclui dummies)
 ├── route_caches[m]             -> Cache com custo e flag 'is_dirty' por máquina
 ├── resource_route_bits[r][m]   -> Bitset de ocupação do recurso 'r' na máquina 'm'
 ├── trial_bits[r]               -> Buffer temporário reutilizável para rota m
 └── trial_bits2[r]              -> Buffer temporário reutilizável para rota l
```

### 3.1 Representação em Bits: cada bit = um slot de tempo

O horizonte de planejamento $H$ é discretizado em slots. Cada slot $t$ corresponde ao **bit $t$** em um vetor de palavras de 64 bits (`uint64_t`). O total de palavras necessárias é:

$$
W = \left\lceil \frac{H + \text{big\_setup}}{64} \right\rceil
$$

O `big_setup` é somado ao horizonte porque a janela de exclusividade de um recurso pode se estender além do término do job.

**Dimensionamento típico** — $H$ geralmente representa **1 semana de produção**, considerando um turno médio de 8 horas por dia com slots de 5 minutos:

$$
H = 7 \text{ dias} \times 8 \text{ h/dia} \times \frac{60 \text{ min}}{5 \text{ min/slot}} = 7 \times 8 \times 12 = 672 \text{ slots}
$$

Supondo `big_setup` desprezável (ou já embutido em $H$), o número de palavras de 64 bits necessárias é:

$$
W = \left\lceil \frac{672}{64} \right\rceil = \left\lceil 10{,}5 \right\rceil = 11 \text{ palavras}
$$

Ou seja, o bitset de ocupação de um recurso em uma máquina ocupa apenas **11 × 8 = 88 bytes** — estrutura mínima que cabe inteiramente em cache L1.

**Exemplo concreto** — horizonte $H = 10$, `big_setup = 2`, job processa nos slots 3–5:

```
Slots:    0  1  2  3  4  5  6  7  8  9  10  11  12
Ocupação: 0  0  0  1  1  1  1  1  1  0   0   0   0
                   ↑           ↑
                 start     end + big_setup - 1
```

O intervalo marcado é $[\text{start},\; \min(H+1,\; \text{end} + \text{big\_setup}))$, ou seja, slots 3 a 7 (inclusive). Em binário, a única palavra de 64 bits que representa esses 13 slots teria os bits 3 a 7 ligados:

```
palavra[0] = 0b 0000...0000 0000 1111 1000
                                     ↑↑↑↑↑
                               bits: 7 6 5 4 3
```

Em notação hexadecimal: `palavra[0] = 0x00F8`.

### 3.2 Marcação do Bitset (`setBits`)

Para ligar os bits do intervalo $[a, b)$ em um vetor de palavras de 64 bits, a função percorre as palavras cobertas e aplica máscaras de bits:

- **Palavra única** ($a$ e $b$ na mesma palavra): máscara com `1`s exatamente em $[a \bmod 64,\; b \bmod 64)$.
- **Múltiplas palavras**: primeira palavra recebe máscara parcial a partir de $a \bmod 64$; palavras intermediárias recebem `0xFFFFFFFFFFFFFFFF` (todos os bits ligados); última palavra recebe máscara parcial até $b \bmod 64$.

**Exemplo** — horizonte $H = 200$, intervalo $[60, 130)$, cobrindo partes das palavras 0, 1 e 2:

```
palavra[0] (bits 0–63):    bits 60–63 ligados  → 0xF000000000000000
palavra[1] (bits 64–127):  todos ligados        → 0xFFFFFFFFFFFFFFFF
palavra[2] (bits 128–191): bits 128–129 ligados → 0x0000000000000003
```

### 3.3 Detecção de Conflito via AND Bitwise

Dado um recurso $r$ compartilhado entre duas máquinas $m$ e $l$, verificar se elas se sobrepõem no tempo é uma operação $\mathcal{O}(W)$:

```cpp
for (int w = 0; w < num_words; w++) {
    if (resource_route_bits[r][m][w] & resource_route_bits[r][l][w]) {
        // conflito: pelo menos um slot está marcado em ambas as rotas
    }
}
```

**Exemplo** — duas rotas disputam o mesmo recurso:

```
Rota m, palavra[1]: 0b ...0001 1111 0000 0000   (slots 72–76 ocupados)
Rota l, palavra[1]: 0b ...0000 0011 1100 0000   (slots 70–73 ocupados)
AND              :  0b ...0000 0011 0000 0000   ≠ 0  →  CONFLITO (slots 72–73)
```

Se o AND resultar em zero para todas as $W$ palavras, não há sobreposição e o movimento é viável para esse recurso.

### 3.4 `RouteCache` e Invalidação Pontual

Cada rota armazena seu custo parcial consolidado e a lista de recursos que tocou (`touched_resources`). Ao aplicar um movimento definitivo, apenas a rota modificada é invalidada via `solution.invalidateRoute(m)` — o bitset `resource_route_bits[r][m]` é zerado e o custo em cache descartado. As demais rotas permanecem válidas (`is_dirty == false`), evitando recálculo desnecessário.

---

## 4. Avaliação Incremental (*Delta Evaluation*) na Busca Local

A busca local explora centenas de alterações hipotéticas por vizinhança. Em vez de chamar o `evaluate()` completo ($\mathcal{O}(M \times N)$), a heurística emprega duas rotinas ultra-rápidas:

### A. Movimentos Intra-Rota: `evaluateIntraRoute(solution, problem_data, m)`

Utilizado pelas vizinhanças **Swap**, **OrOpt-1**, **2-Opt**, **OrOpt-2** e **OrOpt-3**:

1. **Reaproveitamento de Rotas Inalteradas**:
   Soma em $\mathcal{O}(1)$ os custos das rotas $k \ne m$ armazenados em `solution.route_caches[k].cost`.
2. **Simulação Isolada da Rota $m$**:
   Executa `computeRoute` apenas para a rota candidata $m$, gravando a ocupação de recursos no buffer efêmero `solution.trial_bits`.
3. **Checagem de Recursos contra o Estado Commitado**:
   Compara os bits de `trial_bits` exclusivamente contra as outras rotas já commitadas (`resource_route_bits[r][k]`, para $k \ne m$).
4. **Limpeza Otimizada em $\mathcal{O}(R_{\text{touched}})$**:
   A função `clearTrialBuffer` limpa apenas as posições de `trial_bits` que foram efetivamente tocadas, sem percorrer toda a memória.

### B. Movimentos Inter-Rota: `evaluateInterRoute(solution, problem_data, m, l)`

Utilizado pelas vizinhanças **Swap Inter-Rota** e **Realocate Inter-Rota**:

1. **Reaproveitamento das Rotas $k \notin \{m, l\}$**:
   Soma em $\mathcal{O}(1)$ o custo em cache das máquinas que não participam da troca.
2. **Simulação Paralela das Rotas $m$ e $l$**:
   A rota $m$ utiliza o buffer `trial_bits` e a rota $l$ utiliza `trial_bits2`.
3. **Verificação Tríplice de Conflito de Recursos**:
   * Rota $m$ contra Rota $l$ (se compartilham recursos no mesmo intervalo);
   * Rota $m$ contra as demais rotas commitadas ($k \ne m, l$);
   * Rota $l$ contra as demais rotas commitadas ($k \ne m, l$).
4. **Limpeza Rápida**:
   Ambos os buffers de trial são restaurados a zero em tempo proporcional aos recursos tocados.

---

## 5. Resumo de Complexidade das Avaliações

| Operação                         | Escopo                  | Custo Computacional                                             | Quando é Utilizada                                |
| :--------------------------------- | :---------------------- | :-------------------------------------------------------------- | :------------------------------------------------- |
| **`evaluate()`**           | Global (todas as rotas) | $\mathcal{O}(M \cdot N + R \cdot M^2 \cdot W)$                | Construção inicial, perturbação e commit final |
| **`evaluateIntraRoute()`** | 1 Rota ($m$)          | $\mathcal{O}(N_m + R_{\text{touched}} \cdot M \cdot W)$       | Candidatos de Swap, OrOpt-1/2/3, 2-Opt             |
| **`evaluateInterRoute()`** | 2 Rotas ($m, l$)      | $\mathcal{O}(N_m + N_l + R_{\text{touched}} \cdot M \cdot W)$ | Candidatos de SwapInterRoute e Realocate           |

*Onde $M$ é o número de máquinas, $N$ o total de jobs, $N_m$ o número de jobs da rota $m$, $R$ o número de recursos distintos e $W = \lceil (H + \text{big\_setup})/64 \rceil$ o número de palavras do bitset.*
