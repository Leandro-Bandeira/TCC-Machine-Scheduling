# Meta-heurística Iterated Local Search (ILS / GILS-RVND)

Este documento detalha o funcionamento do *framework* **ILS** (*Iterated Local Search*) conforme apresentado no material de referência (`references/o_kit-4.pdf`), cobrindo a arquitetura geral do algoritmo, o procedimento construtivo GRASP e a dinâmica de otimização por busca local e perturbação.

---

## 1. Visão Geral da Meta-heurística ILS

A **Iterated Local Search (ILS)** é uma meta-heurística baseada em busca local que explora o espaço de soluções de forma iterativa. Em vez de reiniciar a busca aleatoriamente ao atingir um ótimo local, o ILS aplica uma **perturbação** controlada na melhor solução corrente para escapar desse ótimo local sem perder a estrutura das boas soluções já construídas.

### **Fluxo de Execução Principal**

```
+--------------------------------------------------------+
|                     maxIter Loops                      |
|                                                        |
|  1. s = Construcao() [GRASP + Inserção Mais Barata]    |
|  2. best = s                                           |
|                                                        |
|  +--------------------------------------------------+  |
|  |             while (iterIls <= maxIterIls)        |  |
|  |                                                  |  |
|  |  a. BuscaLocal(s) [RVND com 5 vizinhanças]      |  |
|  |  b. Se f(s) < f(best):                           |  |
|  |        best = s                                  |  |
|  |        iterIls = 0                               |  |
|  |     Senão:                                       |  |
|  |        s = Perturbacao(best) [Double Bridge]     |  |
|  |        iterIls++                                 |  |
|  +--------------------------------------------------+  |
|                                                        |
|  3. Atualizar bestOfAll                                |
+--------------------------------------------------------+
```

---

## 2. Componentes do Framework ILS

### **2.1. Procedimento de Construção (`Construção()`)**

A fase de construção utiliza uma abordagem gulosa, aleatorizada e adaptativa inspirada no método **GRASP** (*Greedy Randomized Adaptive Search Procedure*) combinada com a técnica de **Inserção Mais Barata**.

1. **Subtour Inicial**: Seleciona $3$ nós aleatórios para formar o ciclo inicial $s' = \{v_1, v_2, v_3, v_1\}$.
2. **Lista de Candidatos ($CL$)**: Armazena todos os vértices ainda não inseridos ($CL = V \setminus V'$).
3. **Cálculo de Custo de Inserção ($\Delta$)**: Para cada nó candidato $k \in CL$ e cada aresta $\{i, j\} \in s'$, calcula-se a variação no custo da função objetivo:
   $$
   \Delta = c_{ik} + c_{kj} - c_{ij}
   $$
4. **Lista de Candidatos Restrita ($RCL$)**: Ordena os pares $(k, \{i, j\})$ em ordem crescente de $\Delta$ e sorteia um elemento aleatório dentro dos primeiros $\lceil \alpha \times |\Omega| \rceil$ pares (onde $\alpha \in [0, 1]$ introduz o grau de aleatoriedade).
5. **Atualização**: Insere o nó $k$ entre $i$ e $j$, remove $k$ da lista $CL$ e repete o processo até que todos os vértices estejam no ciclo.

---

## 3. Busca Local e RVND (`BuscaLocal()`)

Ao obter uma solução construída, o algoritmo executa uma busca local para alcançar um **ótimo local**. A busca local utiliza a estratégia **RVND** (*Random Variable Neighborhood Descent*).

### **Funcionamento do RVND**

* Mantém uma lista com as $5$ estruturas de vizinhança ativas: $NL = \{1, 2, 3, 4, 5\}$.
* A cada passo, seleciona aleatoriamente um índice $n \in NL$.
* Aplica a busca local pela estratégia **Best Improvement** na vizinhança escolhida:
  * Se houver melhora ($f(s') < f(s)$): a solução $s$ é atualizada e a lista $NL$ é **reinicializada** com todas as $5$ vizinhanças ($NL = \{1, 2, 3, 4, 5\}$).
  * Se não houver melhora: a vizinhança $n$ é removida da lista ($NL = NL \setminus \{n\}$).
* O procedimento encerra quando a lista $NL$ fica vazia, garantindo que a solução obtida seja um ótimo local em relação a **todas** as vizinhanças.

---

## 4. Perturbação (`Perturbação()`)

Quando a busca local atinge um ótimo local (sem melhorias), aplica-se um movimento de **perturbação** para alterar a solução corrente mantendo parte substancial de sua estrutura.

* **Movimento Utilizado**: **Double Bridge** (troca de 4 arestas).
* **Mecanismo**: Seleciona dois segmentos não sobrepostos da solução de tamanhos aleatórios entre $2$ e $\lceil |V|/10 \rceil$ e troca a posição desses dois segmentos na sequência.
* **Objetivo**: Saltar para uma nova bacia de atração no espaço de busca sem destruir todo o progresso do ótimo local anterior.

---

## 5. Parâmetros Recomendados

De acordo com o Benchmark do material de referência:

* $\text{maxIter} = 50$: Número de construções completas.
* $\text{maxIterILS}$:
  $$
  \text{maxIterILS} = \begin{cases} \lfloor |V| / 2 \rfloor & \text{se } |V| \ge 150 \\ |V| & \text{caso contrário} \end{cases}
  $$
