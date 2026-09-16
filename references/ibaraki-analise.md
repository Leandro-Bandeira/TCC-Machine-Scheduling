
# Análise Teórica e Computacional da Avaliação de Vizinhanças

**Subtítulo:** Programação Dinâmica, Funções de Penalidade Lineares por Partes e Desafios de Restrições de Recursos Compartilhados
**Contexto Acadêmico:** Agendamento em Máquinas Paralelas ($P \mid r_j, res, s_{ij} \mid \alpha \sum T_j + \beta \sum C_j$)
**Referência Base:** Ibaraki et al. (2005, 2008), Kramer & Subramanian (2019)

---

## 1. A Função de Penalidade Linear por Partes Contínua e Convexa

Considerando o problema de agendamento em máquinas paralelas com datas de liberação ($r_j$), tempos de *setup* dependentes da sequência ($s_{ij}$) e custos de antecipação e atraso, a função de penalidade temporal para uma tarefa $j \in J$ iniciada no instante $t$ é dada pela seguinte formulação contínua e convexa por partes com $\delta = 3$ segmentos:

$$
f_j(t) = \begin{cases} \infty, & \text{se } t < r_j \\[6pt] \beta(t + p_j), & \text{se } r_j \le t \le d_j - p_j \\[6pt] (\alpha + \beta)(t + p_j) - \alpha d_j, & \text{se } t > d_j - p_j \end{cases}
$$

Obtém-se, assim, uma função linear por partes contínua e convexa. A garantia de continuidade nos pontos de inflexão (*breakpoints*) é verificada pelos limites laterais:

* **Em $t = r_j$:** O limite à direita é $\beta(r_j + p_j)$, coincidindo com o início do segundo segmento.
* **Em $t = d_j - p_j$:** O limite à esquerda resulta em $\beta d_j$. Pela direita, tem-se $(\alpha + \beta) d_j - \alpha d_j = \beta d_j$, assegurando a ausência de saltos discretos.
* **Crescimento das Inclinações (Convexidade):** Os coeficientes angulares progridem estritamente ($-M < \beta < \alpha + \beta$), o que satisfaz o requisito fundamental dos algoritmos de Programação Dinâmica de Ibaraki et al. (2008).

### Simplificação: Foco em Data de Liberação ($r_j$) e Atraso ($T_j$)

Considerando apenas a data de liberação ($r_j$) e a penalidade por atraso ($T_j$) — equivalente a adotar $\alpha = 1$ e $\beta = 0$ —, a função de custo linear por partes para cada tarefa iniciada no instante $t$ reduz-se a:

$$
f_j(t) = \begin{cases} \infty, & \text{se } t < r_j \\[6pt] 0, & \text{se } r_j \le t \le d_j - p_j \\[6pt] (t + p_j) - d_j, & \text{se } t > d_j - p_j \end{cases}
$$

---

## 2. Exemplo Ilustrativo de Execução da Programação Dinâmica

Apresenta-se a seguir um exemplo numérico detalhado composto por 5 tarefas em uma única máquina, demonstrando o cálculo do vetor de prefixo ($F_k$) via Programação Dinâmica.

### Parâmetros da Instância

| Tarefa ($j$) | Tempo de Processamento ($p_j$) | Data de Liberação ($r_j$) | Data de Entrega ($d_j$) | *Setup* Anterior ($s_{j-1, j}$) |
| :------------: | :------------------------------: | :---------------------------: | :-----------------------: | :---------------------------------: |
|    $J_1$    |                3                |               0               |             5             |                  0                  |
|    $J_2$    |                2                |               2               |             5             |                  1                  |
|    $J_3$    |                4                |               1               |             7             |                  1                  |
|    $J_4$    |                2                |               7               |             9             |                  0                  |
|    $J_5$    |                3                |               9               |            12            |                  1                  |

### Execução Passo a Passo (Varredura do Prefixo $F$)

A fórmula de atualização do tempo de início mais cedo viável na sequência é dada por $t_k^* = \max\left(r_k, \; t_{k-1}^* + p_{k-1} + s_{k-1, k}\right)$:

1. **Etapa 1 ($J_1$):**

   * $t_1^* = \max(0, 0) = 0 \implies C_1 = 0 + 3 = 3$
   * Atraso: $T_1 = \max(0, 3 - 5) = 0$
   * Prefixo: $F_1 = 0$
2. **Etapa 2 ($J_2$):**

   * $t_2^* = \max(2, 3 + 1) = 4 \implies C_2 = 4 + 2 = 6$
   * Atraso: $T_2 = \max(0, 6 - 5) = 1$
   * Prefixo: $F_2 = 0 + 1 = 1$
3. **Etapa 3 ($J_3$):**

   * $t_3^* = \max(1, 6 + 1) = 7 \implies C_3 = 7 + 4 = 11$
   * Atraso: $T_3 = \max(0, 11 - 7) = 4$
   * Prefixo: $F_3 = 1 + 4 = 5$
4. **Etapa 4 ($J_4$):**

   * $t_4^* = \max(7, 11 + 0) = 11 \implies C_4 = 11 + 2 = 13$
   * Atraso: $T_4 = \max(0, 13 - 9) = 4$
   * Prefixo: $F_4 = 5 + 4 = 9$
5. **Etapa 5 ($J_5$):**

   * $t_5^* = \max(9, 13 + 1) = 14 \implies C_5 = 14 + 3 = 17$
   * Atraso: $T_5 = \max(0, 17 - 12) = 5$
   * Prefixo: $F_5 = 9 + 5 = 14$

### Resultados da Solução Inicial

| Posição ($k$) |      Tarefa      | Início Ótimo ($t_j^*$) | Término ($C_j^*$) | Atraso ($T_j^*$) | Atraso Acumulado ($F_k$) |
| :---------------: | :---------------: | :------------------------: | :------------------: | :----------------: | :------------------------: |
|         1         |      $J_1$      |             0             |          3          |         0         |             0             |
|         2         |      $J_2$      |             4             |          6          |         1         |             1             |
|         3         |      $J_3$      |             7             |          11          |         4         |             5             |
|         4         |      $J_4$      |             11             |          13          |         4         |             9             |
|    **5**    | **$J_5$** |        **14**        |     **17**     |    **5**    |        **14**        |

---

## 3. Avaliação de Movimentos em Tempo Constante $O(1)$ via Sufixo

Considere o teste do movimento de troca (*Swap*) entre as tarefas $J_3$ e $J_4$, gerando a nova sequência $\sigma' = (J_1, J_2, J_4, J_3, J_5)$. Os novos tempos de *setup* são $s_{2,4} = 0$, $s_{4,3} = 1$ e $s_{3,5} = 1$.

### 1. Pré-cálculo da Função de Sufixo ($B_5$)

A função de sufixo $B_5(C)$ expressa o custo restante da rota em função do tempo de término $C$ da tarefa antecedente:

$$
B_5(C) = \max\left(0, \; \max(r_5, \; C + s_{\text{anterior}, 5}) + p_5 - d_5\right)
$$

$$
B_5(C) = \max\left(0, \; \max(9, \; C + 1) + 3 - 12\right)
$$

### 2. Avaliação Direta sem Reprocessar a Cauda

Em vez de simular novamente todas as tarefas após a alteração, conecta-se o prefixo intocado ($F_2$), o bloco reordenado e o sufixo pré-calculado ($B_5$):

* **Prefixo Armazenado ($F_2$):** Término $C_2 = 6$ | Custo acumulado $F_2 = 1$
* **Reavaliação do Bloco Alterado:**
  * $J_4$: $t_3' = \max(7, 6 + 0) = 7 \implies C_4' = 9 \implies T_4' = \max(0, 9 - 9) = 0$
  * $J_3$: $t_4' = \max(1, 9 + 1) = 10 \implies C_3' = 14 \implies T_3' = \max(0, 14 - 7) = 7$
* **Consulta ao Sufixo ($B_5$):**
  $$
  B_5(C_3') = B_5(14) = \max\left(0, \; \max(9, \; 14 + 1) + 3 - 12\right) = \max(0, 18 - 12) = 6
  $$

> **Custo Total Avaliado em Tempo Constante $O(1)$:**
>
> $$
> \text{Custo Total} = F_2 + T_4' + T_3' + B_5(C_3') = 1 + 0 + 7 + 6 = \mathbf{14}
> $$
>
> Variação de Custo ($\Delta$) = $14 - 14 = 0$. O movimento é avaliado instantaneamente sem simular individualmente a posição 5.

### Diferença entre Testar e Aplicar um Movimento

É crucial diferenciar a fase de *avaliação de vizinhança* da fase de *atualização do estado da solução*:

* **Durante a Busca Local (Testes):** Explora-se $O(n^2)$ movimentos candidatos. Cada teste consulta as tabelas $F$ e $B$ já existentes, resultando em custo por teste de $O(1)$. O custo para testar a vizinhança inteira cai de $O(n^3)$ para $O(n^2)$.
* **Ao Aceitar um Movimento (Aplicação):** Quando o melhor movimento é escolhido e a sequência da máquina é alterada, recalculam-se os vetores $F$ e $B$ dessa máquina em tempo linear $O(n)$. Como a atualização é feita apenas uma vez por iteração aceita, o gargalo computacional permanece dominado por $O(n^2)$.

---

## 4. O Impacto do Recurso Compartilhado ($res$)

> ⚠️ **Ruptura da Independência entre Prefixo e Sufixo:**
> A presença de restrições de recursos compartilhados ($res$) em ambiente de máquinas paralelas impede a aplicação direta da avaliação $O(1)$ por Programação Dinâmica.

Quando duas ou mais tarefas que utilizam o mesmo recurso compartilhado ($res_i = res_j$) são processadas em máquinas distintas, a alteração no tempo de início de uma tarefa na Máquina A propaga o consumo do recurso no tempo. Isso pode forçar o adiamento do início de tarefas na Máquina B.

Como consequência, a propriedade de decomposição em prefixos e sufixos independentes deixa de ser válida: o custo do sufixo da Máquina A passa a depender do estado corrente de outras máquinas. Essa interdependência exige verificações globais de viabilidade e temporização, invalidando a premissa de concatenação isolada do algoritmo de Ibaraki et al.
