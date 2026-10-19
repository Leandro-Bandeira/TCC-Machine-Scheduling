# Avaliação de Conflito de Recurso com Intervalos Ordenados e Sweep

Este documento explica em detalhes a técnica de **Intervalos Ordenados e Sweep-Line com `last_end`**, implementada em `src/heuristics/` para acelerar a checagem da restrição de recursos compartilhados (`big_setup` cross-rota).

Na instância `05112025/60` (102 jobs, 10 máquinas paralelas), esta técnica reduziu o tempo de execução de **700 segundos** para **37,9 segundos** (uma aceleração de mais de **18x**), mantendo a exatidão estrita da Função Objetivo.

---

## 1. O Cenário Prático: Exemplo Intuitivo

Para entender o problema e a solução, imagine o seguinte cenário de produção:

* **$M = 3$ máquinas paralelas** ($k = 0, 1, 2$).
* **Tempo de Big Setup**: $big\_setup = 60$ slots.
* **Recurso Compartilhado**: Recurso 7 (por exemplo, um molde ou ferramenta física única que precisa ser compartilhada entre as máquinas).

### Regra do Problema:
Se uma máquina está usando o Recurso 7, **nenhuma outra máquina paralela pode usar esse mesmo recurso ao mesmo tempo**, precisando aguardar a liberação mais o tempo de preparação (`big_setup`).

Portanto, cada job $j$ alocado gera um **intervalo de exclusão temporal** estendido:
$$I_j = [\, start_j, \; \min(H+1, \, end_j + big\_setup) \,)$$

> **Nota sobre Jobs Não Processados (Rota Virtual $M + 1$)**:
> Os jobs que não couberam no planejamento ficam alocados na **rota virtual de índice $M$** (a $(M+1)$-ésima rota, já que as máquinas reais têm índices $0 \dots M-1$). Jobs nessa rota virtual têm `start = -1` e **não geram intervalos nem conflito de recurso**.

### Os Jobs do Exemplo:
Três jobs utilizam o Recurso 7 em máquinas diferentes:

| Job | Máquina ($k$) | Início ($start$) | Fim ($end$) | Intervalo Estendido ($[start, end + 60)$) |
| :---: | :---: | :---: | :---: | :---: |
| **A** | **Máquina 0** | 100 | 130 | **$[100, 190)$** |
| **B** | **Máquina 1** | 50 | 70 | **$[50, 130)$** |
| **C** | **Máquina 2** | 300 | 320 | **$[300, 380)$** |

### Linha do Tempo Visual:

```text
Tempo:    0        50        100      130            190               300        380
          |--------|---------|--------|--------------|-----------------|----------|--->
Máq 0 (A):                   [============= A ==============)  (inicia em 100!)
Máq 1 (B):         [======= B =======)  (libera em 130)
Máq 2 (C):                                                             [=== C ===)
                             ^^^^^^^^^^
                    CONFLITO ENTRE MÁQ 0 E MÁQ 1!
                    (A começa em 100, antes de B liberar em 130)
```

* **Máquina 0 e Máquina 1**: Conflitam no intervalo $[100, 130)$. O par $(0, 1)$ gera **1 violação**.
* **Máquina 2**: Começa apenas no instante $300$, muito depois de a Máquina 0 ter liberado (em $190$). Não conflita com ninguém.

---

## 2. O Que Faz Cada Estrutura de Dados

Para detectar e quantificar esses conflitos em tempo $\mathcal{O}(N)$ (em vez de varrer matrizes gigantes de bits), o código utiliza as seguintes estruturas:

### 2.1. `ResourceInterval` (`src/heuristics/models/solution.hpp`)
Representa um intervalo na linha do tempo. É uma tupla simples com 3 inteiros:
```cpp
struct ResourceInterval {
    int s; // start: início do job
    int e; // end estendido: min(H + 1, end + big_setup)
    int k; // máquina (rota) dona do job (0 .. M-1)
};
```

### 2.2. `G[r]` (`solution.resource_intervals[r]`)
É a **lista global committed** de todos os intervalos de jobs reais que usam o recurso $r$.
* **Propriedade fundamental**: Esta lista é mantida **estritamente ordenada por início**: `(s, k, e)`.
* No nosso exemplo, para o Recurso 7:
  $$G[7] = [\, (50, 130, k=1), \; (100, 190, k=0), \; (300, 380, k=2) \,]$$
* **Quando muda?** Apenas no **commit**, isto é, quando a busca local encontra um movimento que melhora a solução e decide aplicá-lo. Durante a avaliação dos milhares de candidatos vizinhos, $G[r]$ fica intacta em memória compartilhada.

### 2.3. `trial1` e `trial2` (`TrialIntervals`)
São buffers temporários reutilizados usados para simular uma rota modificada sem alterar a solução real:
* Ao testar um movimento intra-rota na Máquina $m$, seus novos intervalos vão para `trial1`.
* Ao testar um movimento inter-rota entre Máquina $m$ e Máquina $l$, os novos intervalos vão para `trial1` (máquina $m$) e `trial2` (máquina $l$).
* **Por que eles já nascem ordenados sem precisar de `sort`?**
  Dentro de qualquer rota válida, os jobs são executados cronologicamente:
  $$start_{j} \ge end_{j-1}$$
  Portanto, conforme o algoritmo percorre a rota candidata calculando os inícios, basta dar `push_back` nos intervalos. Eles **já saem perfeitamente ordenados por início de graça** ($\mathcal{O}(1)$ por job, $\mathcal{O}(|route|)$ no total).

### 2.4. `last_end[k]` (O Vetor de Varredura Sweep)
Durante a varredura linear de um recurso, `last_end[k]` guarda o **instante final do último intervalo processado da máquina $k$**.
* **Para que serve?** Ele responde em $\mathcal{O}(1)$ à pergunta fundamental:
  > *"No instante em que este novo job começa ($s$), a máquina $k$ ainda está ocupando o recurso?"*
  $$\text{Máquina } k \text{ ainda está ocupando o recurso} \iff last\_end[k] > s$$
* Se a resposta for sim, acabamos de descobrir uma sobreposição temporal entre a máquina dona do job atual e a máquina $k$!

### 2.5. `mark_m`, `mark_l`, `pair_mark` e `stamp`
A regra da Função Objetivo estipula que se duas máquinas se sobrepõem 1 vez ou 5 vezes no mesmo recurso, a infração é contada **uma única vez por par de máquinas**.
* Para evitar contar a mesma máquina duas vezes no mesmo recurso, usamos uma marcação com **carimbo numérico (`stamp`)**:
  * Ao detectar conflito com a máquina $k$, checamos: `if (mark_m[k] != stamp)`.
  * Se for diferente, contabilizamos $+1$ violação e atualizamos `mark_m[k] = stamp`.
* **Vantagem de desempenho**: Não é necessário zerar vetores de memória a cada candidato. Basta incrementar `stamp++`.

### 2.6. Cache de Violações: `pair_viol`, `row_viol` e `total_violations`
* `pair_viol[k1 * M + k2]`: número de recursos em que as máquinas $k_1$ e $k_2$ conflitam.
* `row_viol[m]`: soma de todos os conflitos que envolvem a máquina $m$ com qualquer outra máquina.
* `total_violations`: total geral de conflitos da solução corrente.
* **Para que serve?** Permite que qualquer movimento seja avaliado em **tempo $\mathcal{O}(1)$ via delta**:
  $$V_{novo} = V_{total} - \underbrace{V_{antigo}(m)}_{\text{row\_viol}[m]} + \underbrace{V_{trial}(m)}_{\text{calculado pelo sweep}}$$

---

## 3. Como Funciona a Avaliação de Candidatos (O Sweep com `last_end`)

Quando a busca local (RVND) testa alterar a rota da **Máquina 0**, ela não recalcula as outras máquinas. Ela faz um **Sweep de Dois Ponteiros** mesclando:
* **Lista A**: `trial1[7]` (os novos intervalos propostos para a Máquina 0).
* **Lista B**: `G[7]` (os intervalos committed das outras máquinas, ignorando a Máquina 0).

Vamos simular dois candidatos:

---

### Candidato 1 (Movimento Ruim): Atrasar Job A para $start=240, end=270$
* Novo intervalo de A: $[240, 270 + 60) = \mathbf{[240, 330)}$ na Máquina 0.
* Lista A (`trial`): `[(240, 330, k=0)]`
* Lista B (`G` sem máq 0): `[(50, 130, k=1), (300, 380, k=2)]`

O algoritmo consome os intervalos em ordem crescente de início ($s$):

```text
1º Passo: Consome B da Máquina 1 (s=50, e=130)
   - Verifica se a Máquina 0 está ativa: last_end[0] = -∞ > 50? Não.
   - Atualiza last_end[1] = 130.

2º Passo: Consome A da Máquina 0 (s=240, e=330)
   - Verifica se a Máquina 1 está ativa: last_end[1] = 130 > 240? Não (já terminou!).
   - Verifica se a Máquina 2 está ativa: last_end[2] = -∞ > 240? Não (ainda não começou).
   - Atualiza last_end[0] = 330.

3º Passo: Consome C da Máquina 2 (s=300, e=380)
   - Verifica se a Máquina 0 está ativa: last_end[0] = 330 > 300? SIM! (330 > 300)
   --> Conflito detectado entre Máquina 0 e Máquina 2!
   - Atualiza last_end[2] = 380.
```

**Resultado do Candidato 1:**
* Violações antigas da Máquina 0: $V_{antigo}(0) = 1$ (conflitava com Máq 1).
* Novas violações propostas: $V_{trial}(0) = 1$ (passou a conflitar com Máq 2).
* Saldo: $V_{novo} = 1 - 1 + 1 = 1$. Não melhorou a penalidade de recurso.

---

### Candidato 2 (Movimento Vencedor): Atrasar Job A para $start=400, end=430$
* Novo intervalo de A: $[400, 430 + 60) = \mathbf{[400, 490)}$ na Máquina 0.
* Lista A (`trial`): `[(400, 490, k=0)]`
* Lista B (`G` sem máq 0): `[(50, 130, k=1), (300, 380, k=2)]`

Execução do Sweep:

```text
1º Passo: Consome B da Máquina 1 (s=50, e=130)
   - last_end[0] = -∞ > 50? Não.
   - Atualiza last_end[1] = 130.

2º Passo: Consome C da Máquina 2 (s=300, e=380)
   - last_end[0] = -∞ > 300? Não.
   - Atualiza last_end[2] = 380.

3º Passo: Consome A da Máquina 0 (s=400, e=490)
   - Máquina 1 ativa? last_end[1] = 130 > 400? Não.
   - Máquina 2 ativa? last_end[2] = 380 > 400? Não (C terminou em 380!).
   - Atualiza last_end[0] = 490.
```

**Resultado do Candidato 2:**
* $V_{trial}(0) = \mathbf{0}$ (nenhum conflito!).
* Saldo: $V_{novo} = V_{total} - V_{antigo}(0) + V_{trial}(0) = 1 - 1 + 0 = \mathbf{0}$.
* A infração de recurso foi **completamente eliminada**! A FO cai brutalmente (economia da penalidade de recurso). Este movimento é escolhido como o melhor da vizinhança!

---

### 3.1. Passo a Passo Unificado: Merge On-The-Fly (`ig` / `ia`) com `last_end`

Para visualizar a integração exata entre a **disputa dos ponteiros** (ordenação cronológica sem alocar vetores) e a **checagem de conflitos com `last_end`**, considere a simulação de um movimento intra-rota:

* **Cenário:**
  * Recurso compartilhado $R$ entre 3 máquinas paralelas ($0, 1, 2$).
  * Movimento testado na **Máquina 0**: o Job B é alterado para o intervalo $[130, 220)$.
  * **Lista $G$ (jobs committed das outras máquinas):**
    * Posição 0: Job A da **Máq 1** $\rightarrow [100, 190)$
    * Posição 1: Job C da **Máq 2** $\rightarrow [300, 380)$
    *(Cursor `ig = 0`)*
  * **Lista $G'$ (`trial1` - proposta nova da Máquina 0):**
    * Posição 0: Job B da **Máq 0** $\rightarrow [130, 220)$
    *(Cursor `ia = 0`)*
  * **Estado inicial:** `last_end = [-∞, -∞, -∞]`, `violações = 0`.

```text
========================================================================================
RODADA 1:
  - Disputa: Cabeça de G (Job A, s=100) vs Cabeça de G' (Job B, s=130).
             100 < 130 -> Consome Job A (Máquina 1). Avança ig = 1.
  - Checagem last_end: Alguma outra máquina ativa em s=100?
             last_end[0] = -∞ > 100? Não.
             last_end[2] = -∞ > 100? Não.
             -> Nenhum conflito.
  - Atualização: last_end[1] = 190.
  - Estado: last_end = [-∞, 190, -∞] | ig=1, ia=0

RODADA 2:
  - Disputa: Cabeça de G (Job C, s=300) vs Cabeça de G' (Job B, s=130).
             130 < 300 -> Consome Job B (Máquina 0). Avança ia = 1 (G' esgotado).
  - Checagem last_end: Alguma outra máquina ativa em s=130?
             last_end[1] = 190 > 130? SIM! -> CONFLITO (Máquina 0 com Máquina 1)!
             last_end[2] = -∞ > 130? Não.
             -> Violações = 1. (Se abortar no primeiro conflito, a busca para aqui em O(1)!).
  - Atualização: last_end[0] = 220.
  - Estado: last_end = [220, 190, -∞] | ig=1, ia=1

RODADA 3:
  - Disputa: G' esgotado -> Consome o restante de G: Job C (Máquina 2). Avança ig = 2.
  - Checagem last_end: Alguma outra máquina ativa em s=300?
             last_end[0] = 220 > 300? Não (B terminou em 220).
             last_end[1] = 190 > 300? Não (A terminou em 190).
             -> Nenhum conflito.
  - Atualização: last_end[2] = 380.
  - Estado final: last_end = [220, 190, 380] | Listas esgotadas.
========================================================================================
```

**Conclusão do Mecanismo:**
1. O avanço simultâneo de `ig` e `ia` simula um *Merge Sort* ao vivo sem alocar 1 byte sequer de memória adicional.
2. A checagem `last_end[k] > s` valida em $\mathcal{O}(1)$ (uma única comparação de inteiros) se a máquina dona do job atual colide com alguma das outras máquinas.

---

## 4. O Commit: Quando o Movimento é Aceito

Milhares de candidatos são apenas testados e descartados. Quando a busca local encerra a varredura e elege o Candidato 2 como vencedor, ocorre o **Commit**:

1. A rota real da Máquina 0 é atualizada.
2. Na lista global $G[7]$:
   * Remove-se a entrada antiga da Máquina 0 (`[(100, 190, k=0)]`) em tempo linear $\mathcal{O}(n_r)$.
   * A lista remanescente `[(50, 130, k=1), (300, 380, k=2)]` é mesclada com o novo intervalo `[(400, 490, k=0)]` usando `std::merge` em tempo linear $\mathcal{O}(n_r)$.
3. A nova lista committed $G[7]$ fica imediatamente pronta e ordenada:
   $$G[7] = [\, (50, 130, k=1), \; (300, 380, k=2), \; (400, 490, k=0) \,]$$
4. Os caches `pair_viol`, `row_viol` e `total_violations` são atualizados.

---

## 5. Por Que Essa Abordagem é Tão Rápida?

### Comparação de Complexidade:

| Abordagem | Complexidade por Candidato | Operações na Instância 60 ($R=40, M=10, W=12$) |
| :--- | :---: | :---: |
| **Bitsets Anteriores** (`objective.cpp` antigo) | $\mathcal{O}(R \cdot \binom{M}{2} \cdot W)$ | **~21.600 operações de 64 bits** (a cada candidato!) |
| **Intervalos + Sweep Atual** | $\mathcal{O}\big(\sum_{r} (a_r + b_r + a_r \cdot M)\big) \approx \mathbf{\mathcal{O}(N)}$ | **~10 a 30 comparações de inteiros** |

### Por que a economia é colossal?
1. **Esparsidade Real**: Em problemas reais com 102 jobs e 40 recursos, cada recurso só aparece em 2 ou 3 jobs. O bitset anterior gastava 12 palavras inteiras de 64 bits para cada um dos 45 pares de máquinas, varrendo centenas de bits vazios repetidamente.
2. **Avaliação Focada em Deltas**: Se o movimento mexe apenas na Máquina 0, os conflitos entre as Máquinas 1, 2, 3... 9 permanecem intactos no cache. O algoritmo inspeciona exclusivamente os pares que envolvem a Máquina 0.
3. **Custo Diluído**: A ordenação de $G[r]$ só ocorre no commit ($\sim 1$ vez por descida de vizinhança), enquanto o teste de candidatos roda dezenas de milhares de vezes por segundo em pura varredura linear com ponteiros.
