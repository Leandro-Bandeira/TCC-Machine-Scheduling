# Justificativa Teórica e Prática para a Não Utilização do Movimento 2-Opt em Escalonamento (Scheduling)

Este documento explica por que o movimento de vizinhança **2-Opt** (muito popular em problemas de roteamento como TSP/VRP) **não é utilizado** no framework da meta-heurística ILS/RVND do artigo *A unified heuristic and an annotated bibliography for a large class of earliness–tardiness scheduling problems* (Kramer & Subramanian, 2017).

---

## 1. O Funcionamento do Movimento 2-Opt

O movimento **2-Opt** atua invertendo a ordem interna de uma subsequência de tarefas compreendida entre duas posições $i+1$ e $j$:

$$\text{Antes: } [0, \; J_1, \; \mathbf{J_2, \; J_3, \; J_4}, \; J_5, \; 0]$$
$$\text{Depois (2-Opt): } [0, \; J_1, \; \mathbf{J_4, \; J_3, \; J_2}, \; J_5, \; 0]$$

---

## 2. Por que o 2-Opt Funciona Bem no Roteamento (TSP/VRP)?

1. **Simetria das Distâncias**: No TSP/VRP, a matriz de custos de transporte é frequentemente simétrica ($d_{ab} = d_{ba}$).
2. **Preservação da Distância Interna**: Inverter o sentido de percurso de uma rota intermediária não altera a soma das distâncias internas das arestas invertidas.
3. **Eliminação de Cruzamentos**: O movimento remove 2 arestas que se cruzam no plano e conecta 2 novas arestas, sendo ideal para otimizar trajetos geométricos.

---

## 3. Por que o 2-Opt Prejudica o Escalonamento com Prazos (Tardiness / Earliness)?

Diferente do roteamento de veículos, o problema de **Job Scheduling** em máquinas paralelas com datas de entrega (*Due Dates* $d_j$) possui dependência temporal acumulada:

### A. Assimestria dos Prazos de Entrega (*Due Dates*)
* Os tempos de conclusão de cada tarefa dependem estritamente da soma acumulada dos tempos de processamento anteriores:
  $$C_j = \text{Start}_j + p_j$$
* O atraso (*tardiness*) é uma função não linear assimétrica:
  $$T_j = \max\{0, \; C_j - d_j\}$$

### B. Destruição do Alinhamento Temporal
* Quando a busca local constrói uma solução de boa qualidade, as tarefas com prazos mais curtos (*early due dates*) ficam posicionadas no início da sequência para evitar multas por atraso.
* Ao aplicar o **2-Opt**, a ordem interna é **completamente invertida**. A tarefa $J_4$ (que podia ter um prazo tardio) é antecipada, enquanto a tarefa $J_2$ (com prazo super apertado) é empurrada para o final.
* Essa inversão causa um efeito em cadeia que atrasa o término de todas as tarefas da subsequência e das tarefas seguintes, fazendo o atraso total ($\sum w_j T_j$) **explodir**.

---

## 4. A Abordagem Baseada em Blocos (Kramer & Subramanian, 2017)

Conscientes desta limitação estrutural do 2-Opt em problemas com penalidades por atraso e antecipação (E-T), Kramer & Subramanian (2017) substituíram a inversão de subsequências por **movimentos baseados em blocos**:

1. **Inserção de Blocos ($l$-block insertion / OrOpt)**:
   $$\text{Exemplo: } [0, \; 1, \; \mathbf{2, \; 3}, \; 4, \; 5, \; 0] \rightarrow [0, \; 1, \; 4, \; 5, \; \mathbf{2, \; 3}, \; 0]$$
2. **Troca de Blocos ($(l, l')$-block swap)**:
   $$\text{Exemplo: } [0, \; 1, \; \mathbf{2}, \; 3, \; \mathbf{4, \; 5}, \; 0] \rightarrow [0, \; 1, \; \mathbf{4, \; 5}, \; 3, \; \mathbf{2}, \; 0]$$

### Vantagem Crítica da Estrutura de Blocos
* **Preservação da Ordem Interna**: A ordem relativa das tarefas dentro do bloco $B = \{J_2, J_3\}$ é **mantida intacta**.
* Se as tarefas $J_2$ e $J_3$ já estão sequenciadas de forma eficiente entre si, o movimento apenas desloca o bloco inteiro para outra posição ou máquina, sem destruir o sequenciamento relativo interno.

---

## 5. Resumo Comparativo

| Característica | 2-Opt | Inserção/Troca de Blocos (OrOpt / Block Swap) |
| :--- | :--- | :--- |
| **Inverte Ordem Interna?** | **Sim** (Inverte todo o segmento) | **Não** (Preserva a sequência interna) |
| **Impacto no Tardiness** | **Negativo** (Tende a aumentar enormemente o atraso) | **Positivo** (Permite reordenar conjuntos sem quebrar prazos) |
| **Domínio Recomendado** | TSP / VRP (Roteamento de Veículos) | Scheduling ($1\|\sum w_j T_j$, $R\|\sum w_j T_j$) |
| **Presença em Kramer & Subramanian (2017)** | **Ausente** (Descartado) | **Adotado** ($L_{\text{intra}}, L_{\text{inter}}, L'_{\text{intra}}, L'_{\text{inter}}$) |
