# Modelo de Otimização de Sequenciamento (*Time-Index MIP*)

Este documento detalha a formulação matemática do modelo **Time-Index** de Programação Inteira Mista (MIP) utilizado no projeto para o problema de agendamento de produção (*Job Scheduling*) em máquinas paralelas com tempos de setup dependentes da sequência, datas de liberação, prazos e restrições de recursos compartilhados.

---

## 1. Notação e Conjuntos

### **Conjuntos**
* $J$: Conjunto de jobs a serem agendados ($j \in J$).
* $M$: Conjunto de máquinas paralelas ($m \in \{0, \dots, |M|-1\}$).
* $S_j$: Conjunto de slots de tempo válidos para o início do job $j$ ($s \in S_j$), onde $s \ge \text{release\_date\_slot}_j$.
* $R$: Conjunto de recursos compartilhados atrelados aos jobs.

### **Parâmetros**
* $p_j$: Tempo de processamento do job $j$ (em número de slots).
* $d_j$: Prazo de entrega (*due date slot*) do job $j$.
* $r_j$: Data/slot de liberação (*release date slot / not_before_date*) do job $j$.
* $s_{ij}$: Tempo de setup (em slots) entre o término do job $i$ e início do job $j$ na mesma máquina.
* $\Delta$: Tempo de setup global para mudança de recursos compartilhados (*big_setup*).
* $W$: Penalidade (*Big-M*) para jobs não alocados ($W = |J| \times \max(H) + 1$).
* $\epsilon$: Fator de desempate minúsculo ($\epsilon = 1 / W$) para minimizar a soma dos *completion times*.

---

## 2. Variáveis de Decisão

* $x_{j,s,m} \in \{0, 1\}$: Variável binária que assume valor $1$ se o job $j$ inicia exatamente no slot de tempo $s \in S_j$ na máquina $m$; $0$ caso contrário.
* $y_j \in \{0, 1\}$: Variável binária de folga/penalidade que assume valor $1$ se o job $j$ não for alocado no horizonte; $0$ caso contrário.
* $C_j \ge 0$: *Completion time* (slot de término) do job $j$.
* $T_j \ge 0$: *Tardiness* (atraso acumulado) do job $j$.

---

## 3. Função Objetivo

A função objetivo principal minimiza o **atraso total acumulado** (*total tardiness*), penalizando fortemente jobs não alocados ($y_j$) e aplicando um critério secundário de desempate pela **minimização da soma dos tempos de conclusão** ($\sum C_j$):

$$
\min Z = \sum_{j \in J} T_j + W \sum_{j \in J} y_j + \epsilon \sum_{j \in J} C_j
$$

---

## 4. Restrições Matemáticas

### **4.1. Atribuição Única ou Penalidade de Não Alocação**
Cada job $j$ deve ser agendado exatamente uma vez em um slot $s \in S_j$ e máquina $m$, ou ser marcado como não processado ($y_j = 1$):

$$
\sum_{s \in S_j} \sum_{m \in M} x_{j,s,m} + y_j = 1 \quad \forall j \in J
$$

---

### **4.2. Cálculo do Tempo de Término (*Completion Time*)**
O tempo de término $C_j$ de um job alocado no slot $s$ é $s + p_j$:

$$
C_j \ge \sum_{s \in S_j} \sum_{m \in M} (s + p_j) \cdot x_{j,s,m} \quad \forall j \in J
$$

---

### **4.3. Restrição de Atraso (*Tardiness*)**
O atraso $T_j$ de cada job é a diferença positiva entre seu término $C_j$ e a sua data limite $d_j$:

$$
T_j \ge C_j - d_j \quad \forall j \in J
$$

$$
T_j \ge 0 \quad \forall j \in J
$$

---

### **4.4. Não Sobreposição de Jobs e Tempos de Setup (Mesma Máquina)**
Dada uma máquina $m$, dois jobs diferentes $i$ e $j$ não podem se sobrepor nem violar o tempo de setup $s_{ij}$. Se o job $i$ inicia no slot $s$ na máquina $m$, nenhum outro job $j$ pode iniciar dentro da janela de conflito $[s - p_j - s_{ji} + 1, s + p_i + s_{ij} - 1]$:

$$
\sum_{t \in \text{Forbidden}_{ij}(s)} x_{j,t,m} \le 1 - x_{i,s,m} \quad \forall i, j \in J (i \neq j), \forall m \in M, \forall s \in S_i
$$

Onde a janela de slots proibidos $\text{Forbidden}_{ij}(s)$ é definida por:

$$
\text{Forbidden}_{ij}(s) = \left\{ t \in S_j \;\middle|\; s - p_j - s_{ji} + 1 \le t \le s + p_i + s_{ij} - 1 \right\}
$$

---

### **4.5. Restrição de Recursos Compartilhados (Entre Máquinas Distintas)**
Se dois jobs $i$ e $j$ compartilham o mesmo recurso restrito e são processados em máquinas paralelas distintas ($m \ne m'$), deve-se respeitar o tempo de mudança/setup global $\Delta$ entre eles:

$$
x_{i,s,m} + \sum_{m' \in M, m' \ne m} \sum_{t \in \text{ForbiddenResource}_{ij}(s)} x_{j,t,m'} \le 1 \quad \forall (i, j) \in R, \forall m \in M, \forall s \in S_i
$$

Onde a janela restrita por recurso é:

$$
\text{ForbiddenResource}_{ij}(s) = \left\{ t \in S_j \;\middle|\; s - p_j - \Delta + 1 \le t \le s + p_i + \Delta - 1 \right\}
$$

---

## 5. Implementação no Repositório

* **Modelo Exato (Pyomo)**: Implementado em [`src/main/optimize.py`](file:///home/leandro-bandeira/Documents/me/TCC/TCC-Machine-Scheduling/src/main/optimize.py). Resolvido via solvers de classe industrial como **HiGHS** ou **Gurobi**.
* **Heurística ILS (C++17)**: Implementada em [`src/heuristics/`](file:///home/leandro-bandeira/Documents/me/TCC/TCC-Machine-Scheduling/src/heuristics/), utilizando a mesma matriz de setup e tempos para otimizar as rotas/máquinas em paralelo via busca local (VNS).
