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

Para a transferência e reequilíbrio de carga entre máquinas paralelas distintas:

### 3.1. $k$-block insertion inter-machine (Realocate Inter-Máquina)
* **Implementação C++**: `bestImprovementRealocate(problemData, solution, k)`
  * Para $k = 1$: Realoca 1 único job de uma máquina $m$ para uma posição $j$ da máquina $l$.
  * Para $k = 2$: Realoca um bloco contíguo de 2 jobs $\{J_i, J_{i+1}\}$ da máquina $m$ para a máquina $l$, preservando a ordem relativa do bloco.
* **Guarda de Segurança (Tamanho mínimo)**: A rota de origem $m$ precisa conter pelo menos **$k$ jobs reais** ($\ge 2 + k$ elementos incluindo os *dummies*).

### 3.2. $(1, 1)$-block swap inter-machine (Swap Inter-Máquina 1x1)
* **Implementação C++**: `bestImprovementSwapInterRoute(problemData, solution)`
* **Descrição**: Troca um job $J_i$ da rota $m$ por um job $J_j$ da rota $l$ ($m < l$, simétrico).

---

## 4. Tabela Resumo e Mapeamento C++ (As 6 Vizinhanças do RVND)

O procedimento RVND opera com as seguintes 6 estruturas de vizinhança ativas (`NL = {1, 2, 3, 4, 5, 6}`):

| ID | Vizinhança | Tamanho ($l, l'$) | Função C++ Correspondente | Condição Rota Origem |
| :-: | :--- | :--- | :--- | :--- |
| **1** | **Swap Intra** | $(1, 1)$ | `bestImprovementSwap(...)` | Jobs Reais $\ge 2$ |
| **2** | **OrOpt-1 Intra** | $l = 1$ | `bestImprovementOrOpt(..., k=1)` | Jobs Reais $\ge 2$ |
| **3** | **OrOpt-2 Intra** | $l = 2$ | `bestImprovementOrOpt(..., k=2)` | Jobs Reais $\ge 3$ |
| **4** | **Swap Inter** | $(1, 1)$ | `bestImprovementSwapInterRoute(...)` | Origem $\ge 1$, Destino $\ge 1$ |
| **5** | **Realocate Inter (k=1)** | $l = 1$ | `bestImprovementRealocate(..., k=1)` | Origem $\ge 1$, Destino $\ge 0$ |
| **6** | **Realocate Inter (k=2)** | $l = 2$ | `bestImprovementRealocate(..., k=2)` | Origem $\ge 2$, Destino $\ge 0$ |

---

## 5. Análise sobre Movimentos Descartados

### 5.1. Swap Inter-Máquina $(1, 2)$ e Blocos Maiores $(l, l')$
No artigo (Kramer & Subramanian, 2017/2019, Tabela 9), os autores avaliaram trocas inter-máquinas com blocos assimétricos como $(1, 2)$, $(1, 3)$ e $(2, 2) \dots (4, 4)$. No entanto, esse operador foi **deliberadamente descartado** no nosso projeto pelas seguintes razões:

1. **Alcançabilidade por Composição no RVND:**
   A troca de 1 job por um bloco de 2 jobs já pode ser atingida em 2 passos pelo RVND através da combinação sucessiva de **Swap Inter $(1, 1)$** e **Realocate Inter ($k=1$ ou $k=2$)**. Não há ganho estrutural que justifique uma vizinhança combinada específica.

2. **Impacto em Setups Dependentes da Sequência ($s_{ij}$):**
   Um movimento Swap $(1, 2)$ desfaz e refaz **6 arestas de setup simultaneamente** (3 na rota $m$ e 3 na rota $l$). A probabilidade de 6 transições independentes melhorarem conjuntamente a função objetivo é extremamente baixa.

3. **Restrição Crítica de Recursos Compartilhados (`big_setup` cross-machine):**
   Mover simultaneamente 1 job para uma máquina e 2 jobs para outra amplia drasticamente o risco de violação temporal de recursos compartilhados com as demais máquinas da instância, acionando penalidades severas que descartam o movimento. Movimentos atômicos (Realocate $k=1$ ou $k=2$) são muito mais eficazes para encontrar janelas livres viáveis nos turnos.

4. **Explosão Computacional com Ganho Marginal:**
   * No artigo (Tabela 9), a adição do Swap $(1, 2)$ sobre o Swap $(1, 1)$ representou um ganho médio de apenas **+0.28%** (de 68.04% para 68.32%) em problemas sem restrições de turno e recursos.
   * Em contrapartida, sua busca é assimétrica e exige complexidade $\mathcal{O}(M^2 \cdot N_m \cdot N_l)$, onerando substancialmente o tempo de CPU com checagens de bitsets (`evaluateInterRoute`).

### 5.2. 2-Opt
* Descartado por inverter a ordem de subsequências e causar destruição generalizada no atendimento aos prazos de entrega (*due dates*), conforme fundamentado em [`why_no_2opt.md`](file:///home/leandro-bandeira/Documents/me/TCC/TCC-Machine-Scheduling/heuristics_information/why_no_2opt.md).

### 5.3. Inserção Intra de Blocos Maiores ($l \ge 3$)
* Descartados na calibração por não apresentarem ganhos de qualidade que compensem o custo adicional de exploração dentro de rotas já otimizadas com OrOpt-1 e OrOpt-2.
