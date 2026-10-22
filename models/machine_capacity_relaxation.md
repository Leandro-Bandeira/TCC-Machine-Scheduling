# Fortalecimento da Relaxação Linear: Clique de Capacidade por Slot

Este documento explica por que a restrição de capacidade por slot na máquina ($\sum_j \sum_s x_{j,s,m} \le 1$) aperta significativamente a relaxação linear (LP) do modelo **Time-Index MIP**, mesmo quando já existe uma restrição de não sobreposição e setup par-a-par.

---

## 1. Formulação da Restrição de Capacidade por Slot

Para cada máquina $m \in M$ e cada slot de início válido $t \in S_{\text{machine}}$, no máximo **1 job** pode estar ativo (em processamento) no instante $t$:

$$
\sum_{j \in J} \sum_{s \in S_j \,:\, t - p_j + 1 \le s \le t} x_{j,s,m} \le 1 \quad \forall t \in S_{\text{machine}}, \forall m \in M
$$

Onde o intervalo $[t - p_j + 1, \, t]$ compreende todos os slots de início $s$ nos quais o job $j$ (com duração $p_j$) já iniciou em ou antes de $t$ e ainda não concluiu seu processamento no slot $t$ (isto é, $s \le t \le s + p_j - 1$).

---

## 2. Por que a Restrição de Setup Par-a-Par Não Basta na Relaxação Linear?

A restrição de não sobreposição e setup entre pares de jobs $i \neq j$ é definida por:

$$
x_{i,t,m} + \sum_{s \in \text{Forbidden}_{ij}(t)} x_{j,s,m} \le 1 \quad \forall i, j \in J (i \neq j), \forall m \in M, \forall t \in S_i
$$

Para **soluções inteiras** ($x \in \{0, 1\}$), essa restrição com $s_{ij} \ge 0$ já é suficiente para impedir qualquer sobreposição física entre jobs na mesma máquina.

Entretanto, durante a resolução por *Branch-and-Bound*, o solver resolve a **relaxação linear** ($0 \le x_{j,s,m} \le 1$) para calcular o limite inferior (*lower bound* / *dual bound*). Na relaxação linear, a formulação par-a-par permite superposições fracionárias severas devido a **duas causas matemáticas**:

---

### Causa 1: Restrições de Aresta (Par-a-Par) vs. Restrição de Clique (Todos os Jobs)

A restrição de setup testa apenas **dois jobs $(i, j)$ por vez**. Em Teoria dos Grafos, isso equivale a impor $x_i + x_j \le 1$ para cada aresta de um grafo de conflito completo $K_{|J|}$, em vez de impor que a soma de todos os vértices do clique seja $\le 1$.

#### **Exemplo Numérico ($|J| = 10$ jobs no mesmo slot $t=0$)**
Considere $10$ jobs idênticos que desejam iniciar no slot $t=0$ na mesma máquina $m=0$. Na relaxação linear, o solver pode atribuir:

$$
x_{1,0,0} = 0.5, \quad x_{2,0,0} = 0.5, \quad \dots, \quad x_{10,0,0} = 0.5
$$

1. **Na restrição de setup par-a-par**:
   Para qualquer par $(i, j)$, temos:
   $$
   x_{i,0,0} + x_{j,0,0} = 0.5 + 0.5 = 1.0 \le 1 \quad (\text{Viável no LP!})
   $$
   Todas as restrições par-a-par são satisfeitas, mas a máquina está processando $\sum_{j=1}^{10} 0.5 = \mathbf{5.0}$ **jobs simultaneamente** no slot $t=0$. De forma geral, o ótimo fracionário permite empilhar até $|J|/2$ jobs ao mesmo tempo na mesma máquina.

2. **Com a restrição de Clique de Capacidade por Slot**:
   Todos os $10$ jobs entram na **mesma** inequação no slot $t=0$:
   $$
   \sum_{j=1}^{10} x_{j,0,0} \le 1
   $$
   O valor máximo simétrico cai de $0.5$ para $0.1$, limitando a ocupação total da máquina no slot $t=0$ a exatamente $1.0$.

---

### Causa 2: Pulverização Fracionária de $x_{i,t,m}$ ao Longo do Tempo

Mesmo quando há apenas **2 jobs** ($A$ e $B$), a restrição de setup par-a-par coloca apenas **um único slot $t$** do job $i$ ($x_{i,t,m}$) contra a soma na janela proibida do job $j$:

$$
x_{A,t,m} + \sum_{s = t - p_B - s_{BA} + 1}^{t + p_A + s_{AB} - 1} x_{B,s,m} \le 1
$$

Se o solver pulverizar o início do job $A$ em múltiplos slots consecutivos, $x_{A,t,m}$ será pequeno em cada slot individual, enfraquecendo o lado direito ($1 - x_{A,t,m}$) da restrição.

#### **Exemplo Numérico (2 jobs com duração $p_A = p_B = 4$ e setup $0$)**
Suponha que a relaxação linear distribua o início dos jobs $A$ e $B$ nos slots $s \in \{0, 1, 2, 3\}$:
* $x_{A,0,0} = x_{A,1,0} = x_{A,2,0} = x_{A,3,0} = 0.25$ (soma total de $A = 1.0$)
* $x_{B,0,0} = x_{B,1,0} = x_{B,2,0} = x_{B,3,0} = 0.18$ (soma de $B = 0.72$ na mesma janela)

1. **Na restrição de setup par-a-par (para qualquer $t \in \{0, 1, 2, 3\}$)**:
   $$
   \underbrace{x_{A,t,0}}_{0.25} + \underbrace{(x_{B,0,0} + x_{B,1,0} + x_{B,2,0} + x_{B,3,0})}_{0.72} = 0.97 \le 1 \quad (\text{Viável no LP!})
   $$
   Observe o que ocorre no slot $t=3$: como $p_A = 4$, todas as frações de $A$ iniciadas em $s \in \{0, 1, 2, 3\}$ ainda estão em execução em $t=3$ (ocupando $0.25 \times 4 = 100\%$ da máquina), enquanto $B$ ocupa simultaneamente $72\%$ da mesma máquina (ocupação total de **$172\%$**). Isso ocorre porque a restrição de setup avaliou apenas $x_{A,3,0} = 0.25$ isoladamente, ignorando que $x_{A,0,0}, x_{A,1,0}$ e $x_{A,2,0}$ também estavam ativos em $t=3$.

2. **Com a restrição de Clique de Capacidade no slot $t=3$**:
   A restrição soma toda a janela ativa $[0, 3]$ **tanto para $A$ quanto para $B$**:
   $$
   \sum_{s=0}^{3} x_{A,s,0} + \sum_{s=0}^{3} x_{B,s,0} = 1.00 + 0.72 = 1.72 \nleq 1 \quad (\text{Cortado imediatamente!})
   $$

---

## 3. Resumo Comparativo

| Propriedade | Sem Clique de Capacidade (Apenas Setup Par-a-Par) | Com Clique de Capacidade por Slot |
| :--- | :--- | :--- |
| **Validade para Soluções Inteiras ($x \in \{0,1\}$)** | Exata (sem sobreposição) | Exata (sem sobreposição) |
| **Ocupação Máxima da Máquina na Relaxação LP** | Até $\frac{|J|}{2}$ jobs simultâneos no mesmo slot | No máximo **$1.0$** job por slot e máquina |
| **Resistência à Pulverização Fracionária de Inícios** | Fraca ($x_{i,t,m}$ isolado em um único slot $t$) | Forte (soma todo o intervalo ativo $[t - p_j + 1, t]$ de cada job) |
| **Custo Computacional (Número de Linhas)** | $\mathcal{O}(|J|^2 \cdot |T| \cdot |M|)$ | Apenas $\mathcal{O}(|T| \cdot |M|)$ linhas adicionais |
