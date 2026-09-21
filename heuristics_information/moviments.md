# Movimentos e Vizinhanças da Heurística no Código C++ (`src/heuristics/`)

Este documento detalha o funcionamento exato das **estruturas de vizinhança** e dos **movimentos de busca local e perturbação** implementados no código C++ do projeto (`src/heuristics/algorithms/LocalSearch.cpp` e `src/heuristics/algorithms/ils.cpp`).

---

## 1. Estrutura das Soluções e Avaliação

### **Representação da Solução (`Solution`)**
No código C++, a solução é representada por `count_machines` rotas/máquinas paralelas (`solution.routes`). Cada rota possui o formato:
$$
\text{route}_m = [\text{Dummy}, \; \text{Job}_1, \; \text{Job}_2, \; \dots, \; \text{Job}_k, \; \text{Dummy}]
$$
* Os **Dummies** (nó $0$ nas pontas) nunca são movidos por nenhuma vizinhança.
* A função objetivo total $f(s)$ avalia o atraso acumulado (*tardiness*), o tempo de conclusão (*completion time*) e penaliza severamente conflitos de setup de recursos compartilhados (*big_setup* cross-rota).

### **Estratégia de Descida: *Best Improvement***
Para cada vizinhança, o algoritmo explora **todos** os vizinhos válidos e seleciona aquele com a maior redução no valor da função objetivo ($\Delta < 0$). Se houver melhora, atualiza a solução e retorna `true`; caso contrário, retorna `false`.

---

## 2. As 7 Estruturas de Vizinhança do RVND (`LocalSearch::algorithm`)

O procedimento **RVND** (*Random Variable Neighborhood Descent*) sorteia aleatoriamente entre $7$ vizinhanças ativas ($NL = \{1, 2, 3, 4, 5, 6, 7\}$).

Se uma vizinhança encontra melhora, o vetor $NL$ é reinicializado com todas as $7$ vizinhanças. Se não houver melhora, a vizinhança é removida de $NL$ em $\mathcal{O}(1)$ via `swap + pop_back`. O RVND encerra quando $NL$ fica vazio (ótimo local simultâneo em todas as 7 vizinhanças).

---

### **A. Movimentos Intra-Rota (Vizinhanças 1 a 5)**

Estes movimentos atuam dentro de cada rota $m \in \{0, \dots, \text{count\_machines}-1\}$ individualmente:

#### **1. Swap Intra-Rota (`bestImprovementSwap` — Vizinhança 1)**
* **Operação**: Troca a posição de dois jobs $v_i$ e $v_j$ dentro da mesma rota ($1 \le i < j < \text{size}-1$).
* **Simetria**: Simétrico. A busca itera $j$ a partir de $i+1$.
* **Exemplo**: $[D, 1, \mathbf{2}, 3, \mathbf{4}, 5, D] \rightarrow [D, 1, \mathbf{4}, 3, \mathbf{2}, 5, D]$.

#### **2. OrOpt-1 / Reinsertion (`bestImprovementOrOpt(k=1)` — Vizinhança 2)**
* **Operação**: Remove um único job da posição $i$ e o reinsere na posição $j$ da mesma rota.
* **Assimestria**: Assimétrico. O destino $j$ varre todo o intervalo válido da rota pós-remoção ($j \ne i$).
* **Exemplo**: $[D, 1, \mathbf{2}, 3, 4, 5, D] \rightarrow [D, 1, 3, 4, 5, \mathbf{2}, D]$.

#### **3. 2-Opt (`bestImprovement2Opt` — Vizinhança 3)**
* **Operação**: Inverte a ordem da subsequência de jobs entre a posição $i+1$ e $j$ na mesma rota ($j \ge i+2$).
* **Simetria**: Simétrico. O limite inicial é $j = i+2$.
* **Exemplo**: $[D, 1, 2, \mathbf{3, 4, 5}, 6, D] \rightarrow [D, 1, 2, \mathbf{5, 4, 3}, 6, D]$.

#### **4. OrOpt-2 (`bestImprovementOrOpt(k=2)` — Vizinhança 4)**
* **Operação**: Remove um bloco de $2$ jobs consecutivos $\{v_i, v_{i+1}\}$ e o reinsere na posição $j$ da mesma rota, preservando a ordem interna do bloco.
* **Exemplo**: $[D, 1, \mathbf{2, 3}, 4, 5, D] \rightarrow [D, 1, 4, 5, \mathbf{2, 3}, D]$.

#### **5. OrOpt-3 (`bestImprovementOrOpt(k=3)` — Vizinhança 5)**
* **Operação**: Remove um bloco de $3$ jobs consecutivos $\{v_i, v_{i+1}, v_{i+2}\}$ e o reinsere na posição $j$ da mesma rota, preservando a ordem interna do bloco.
* **Exemplo**: $[D, 1, \mathbf{2, 3, 4}, 5, 6, D] \rightarrow [D, 1, 5, 6, \mathbf{2, 3, 4}, D]$.

---

### **B. Movimentos Inter-Rota (Vizinhanças 6 e 7)**

Estes movimentos transferem ou trocam jobs **entre máquinas paralelas distintas**:

#### **6. Swap Inter-Rota (`bestImprovementSwapInterRoute` — Vizinhança 6)**
* **Operação**: Troca um job $v_i$ da rota $m$ por um job $v_j$ da rota $l$ ($m < l$).
* **Aplicação**: Permite reequilibrar o mix de produtos e reduzir setups entre máquinas paralelas.
* **Simetria**: Simétrico ($m < l$).
* **Exemplo**:
  - Rota $m$: $[D, a_1, \mathbf{a_2}, a_3, D]$
  - Rota $l$: $[D, b_1, \mathbf{b_2}, D]$
  - Após Swap Inter-Rota:
    - Rota $m$: $[D, a_1, \mathbf{b_2}, a_3, D]$
    - Rota $l$: $[D, b_1, \mathbf{a_2}, D]$

#### **7. Realocate Inter-Rota (`bestImprovementRealocate` — Vizinhança 7)**
* **Operação**: Remove um job $v_i$ da rota $m$ e o insere na posição $j$ da rota $l$ ($m \neq l$).
* **Aplicação**: Transfere carga de trabalho entre máquinas para mitigar atrasos e melhorar o nivelamento da produção.
* **Assimestria**: Assimétrico (itera todos os pares $m \ne l$).
* **Exemplo**:
  - Rota $m$: $[D, a_1, \mathbf{a_2}, a_3, D]$
  - Rota $l$: $[D, b_1, b_2, D]$
  - Após Realocate:
    - Rota $m$: $[D, a_1, a_3, D]$
    - Rota $l$: $[D, b_1, \mathbf{a_2}, b_2, D]$

---

## 3. Movimento de Perturbação (`ILS::perturbation`)

A perturbação no código C++ adapta sua estratégia dependendo da quantidade de máquinas disponíveis na instância:

1. **Instâncias Monomáquina ($\text{count\_routes} == 1$)**:
   - Aplica o **$(l, l')$-Block Swap Intra-Máquina**: Sorteia dois blocos de jobs $A$ (tamanho $l$) e $B$ (tamanho $l'$) com $l, l' \in [2, \lfloor N/4 \rfloor]$ e troca a posição deles dentro da única rota.

2. **Instâncias multimáquinas ($\text{count\_routes} > 1$)**:
   - Aplica a **Inserção Múltipla Inter-Máquinas**: Seleciona jobs de uma máquina e os insere em outra máquina diferente (repetido de $1$ a $3$ vezes aleatoriamente), promovendo a redistribuição da demanda entre as máquinas paralelas.
