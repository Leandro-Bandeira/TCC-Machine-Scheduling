# Movimentos de Vizinhança Baseados em Blocos e Escolha de Tamanhos (Baseado em Kramer & Subramanian, 2017)

Este documento descreve os movimentos de busca local e perturbação baseados em blocos propostos no artigo *A unified heuristic and an annotated bibliography for a large class of earliness–tardiness scheduling problems* (Kramer & Subramanian, 2017), bem como os tamanhos de blocos calibrados pelos autores e o mapeamento direto com as funções C++ implementadas no projeto (`src/heuristics/algorithms/LocalSearch.cpp`).

---

## 1. Conceito de Bloco

Um **bloco** $B$ de tamanho $l$ em uma máquina $k$ é definido como uma subsequência contígua de $l$ tarefas executadas em sequência nessa máquina:

$$B = (\pi_k(i), \pi_k(i+1), \dots, \pi_k(i+l-1))$$

---

## 2. Movimentos Intra-Máquina Adotados

O algoritmo RVND (*Random Variable Neighborhood Descent*) opera com as seguintes vizinhanças intra-máquina calibradas no artigo:

### 2.1. $1$-block e $2$-block insertion intra-machine (Inserção Intra-máquina)
* **Implementação C++**: `bestImprovementOrOpt(problemData, solution, k)`
  * Para $l = 1$: `bestImprovementOrOpt(..., k=1)` (*Reinsertion / OrOpt-1*).
  * Para $l = 2$: `bestImprovementOrOpt(..., k=2)` (*OrOpt-2*).
* **Descrição**: Remove um bloco de tamanho $k$ ($k \in \{1, 2\}$) da posição $i$ de uma máquina e o insere na posição $j$ da própria máquina.
* **Exemplo ($k=2$)**:
  $$\text{Rota original: } [0, \; 1, \; \mathbf{2, \; 3}, \; 4, \; 5, \; 0]$$
  $$\text{Após inserção: } [0, \; 1, \; 4, \; 5, \; \mathbf{2, \; 3}, \; 0]$$
* **Guarda de Segurança (Tamanho mínimo)**: A rota precisa conter pelo menos **$k + 1$ jobs reais** (ou seja, $\ge k + 3$ elementos com os dummies). Para $k=2$, são necessários no mínimo 3 jobs reais (`[0, 1, 2, 3, 0]`).

### 2.2. $(1, 1)$-block swap intra-machine (Troca Intra-máquina)
* **Implementação C++**: `bestImprovementSwap(problemData, solution)` (*Swap tradicional 1x1*).
* **Descrição**: Troca as posições de dois jobs individuais $J_i$ e $J_j$ dentro da mesma máquina ($l=1, l'=1$).
* **Exemplo**:
  $$\text{Rota original: } [0, \; 1, \; \mathbf{2}, \; 3, \; \mathbf{4}, \; 5, \; 0]$$
  $$\text{Após swap: } [0, \; 1, \; \mathbf{4}, \; 3, \; \mathbf{2}, \; 5, \; 0]$$
* **Guarda de Segurança (Tamanho mínimo)**: A rota precisa conter pelo menos **2 jobs reais** ($\ge 4$ elementos com os dummies).

---

## 3. Movimentos Inter-Máquinas Adotados

Para a transferência e reequilíbrio de carga entre máquinas distintas paralelas ($L_{\text{inter}} = \{1, 2\}$ e $L'_{\text{inter}}$):

1. **$l$-block insertion inter-machine ($l \in \{1, 2\}$)**:
   * **C++**: `bestImprovementRealocate` (para $l=1$) ou realocação de bloco de 2 jobs entre máquinas.
2. **$(l, l')$-block swap inter-machine**:
   * **C++**: `bestImprovementSwapInterRoute` (para $(1,1)$) e trocas cruzadas de blocos de tamanhos $(1,1) \dots (4,4)$.

---

## 4. Tabela Resumo e Mapeamento C++

| Vizinhança | Tamanho ($l, l'$) | Função C++ Correspondente | Condição Rota Origem |
| :--- | :--- | :--- | :--- |
| **1-block insert Intra** | $l = 1$ | `bestImprovementOrOpt(..., k=1)` | Jobs Reais $\ge 2$ |
| **2-block insert Intra** | $l = 2$ | `bestImprovementOrOpt(..., k=2)` | Jobs Reais $\ge 3$ |
| **(1,1) swap Intra** | $(1, 1)$ | `bestImprovementSwap(...)` (Swap tradicional 1x1) | Jobs Reais $\ge 2$ |
| **1-block insert Inter** | $l = 1$ | `bestImprovementRealocate(...)` | Origem $\ge 1$, Destino $\ge 0$ |
| **(1,1) swap Inter** | $(1, 1)$ | `bestImprovementSwapInterRoute(...)` | Origem $\ge 1$, Destino $\ge 1$ |

---

## 5. Nota sobre Movimentos Descartados (2-Opt e Blocos Maiores Intra)

* **2-Opt**: Descartado por inverter a ordem de subsequências e causar destruição no alinhamento de prazos de entrega (*due dates*), conforme detalhado em [`why_no_2opt.md`](file:///home/leandro-bandeira/Documents/me/TCC/TCC-Machine-Scheduling/heuristics_information/why_no_2opt.md).
* **3-block insert intra e $(l,l') > (1,1)$ intra**: Descartados na calibração do artigo por não apresentarem ganhos em relação ao custo computacional.
