# Avaliação de Conflito de Recurso com Intervalos Ordenados e Sweep

Este documento descreve uma **proposta** (ainda não implementada) para reduzir o custo da checagem da restrição de recurso compartilhado (`big_setup` cross-rota) na avaliação da FO da heurística ILS/RVND em `src/heuristics/`.

---

## 1. O problema que a restrição resolve

Dois jobs do **mesmo recurso**, em **máquinas (rotas) diferentes**, não podem se sobrepor no tempo. A janela de cada job é estendida pelo `big_setup`:

$$
I_j = [\, start_j,\ \min(H+1,\ end_j + big\_setup)\,)
$$

* Jobs na **mesma** máquina podem ter janelas que se tocam sem problema.
* Jobs **não processados (não alocados)** são aqueles que estão na rota virtual de índice `M` (a rota `M + 1`, com `M = count_machines` e índices `0..M-1` para as máquinas reais). Eles **não geram intervalo**. Jobs de uma máquina real com `start > H` também ficam não alocados e também não geram intervalo.
* Os intervalos são **semiabertos** $[s, e)$. Dois intervalos $a$ e $b$ se sobrepõem quando:

$$
a.s < b.e \quad \text{e} \quad b.s < a.e
$$

### Penalidade atual na FO

Para cada recurso $r$, a FO soma 1 por **par de máquinas** $(k_1, k_2)$ que viola a restrição, contando o par **uma única vez** mesmo que haja várias sobreposições. O total é multiplicado por `resource_violation_penalty`.

---

## 2. Como é feito hoje

Em `src/heuristics/utils/objective.cpp`:

* `computeRoute` marca, no bitset do recurso do job, os slots `[start, end + big_setup)` via `set_range`.
* `countResourceViolations` percorre **todos os recursos** e **todos os pares de máquinas**, fazendo AND entre bitsets de $W$ palavras de 64 bits.

Custo por avaliação de candidato:

$$
O(R \cdot \tbinom{M}{2} \cdot W)
$$

Na instância `05112025/60` ($R = 40$, $M = 10$, $W = 12$) são cerca de **21 600** ANDs, para **cada candidato**. O `computeRoute` de uma rota (~10 jobs) é duas ordens de grandeza mais barato. A checagem de recurso é o gargalo.

Boa parte desse trabalho é redundante: um movimento só altera a rota $m$ (ou $m$ e $l$). Os pares de máquinas que **não envolvem** $m$ (ou $l$) têm o mesmo resultado de antes.

---

## 3. Visão geral da proposta

1. Representar cada job por um **intervalo** em vez de pintar bits.
2. Guardar, por recurso, a lista de intervalos de todas as máquinas, **ordenada por início**.
3. Manter o total de violações $V_{total}$ da solução corrente.
4. Na avaliação de um candidato, recalcular **apenas** as violações da rota alterada com um **sweep** (varredura) e obter:

$$
V_{novo} = V_{total} - V_{antigo}(m) + V_{trial}(m)
$$

5. A estrutura global só é atualizada no **commit**, quando um movimento é aceito.

---

## 4. Estruturas de dados

| Estrutura                | Conteúdo                                                                                            | Quando muda                                  |
| ------------------------ | ---------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| `G[r]`                 | Lista de`(start, end_estendido, k)` de todos os jobs do recurso `r`, ordenada por `(start, k)` | Só no commit                                |
| `trial[r]`             | Intervalos de`r` da rota candidata `m`, em ordem de rota                                         | A cada candidato (buffer reutilizável)      |
| `V_total`              | Nº total de violações (pares de máquinas por recurso) da solução corrente                      | Só no commit                                |
| `V_antigo(m)`          | Violações da rota`m` na solução corrente                                                       | Uma vez por rota na varredura da vizinhança |
| `touched_resources[m]` | Recursos tocados pela rota`m`                                                                      | Já existe em`RouteCache`                  |

---

## 5. Por que as listas ficam ordenadas sem `sort`

Dentro de uma rota, cada job começa só depois do término do anterior:

$$
start_j \ge last\_completion = end_{j-1}
$$

Logo, ao longo da rota, os **inícios** e os **fins** (inclusive `end + big_setup`) são **não decrescentes**.

Consequências:

1. Ao percorrer a rota no `computeRoute` e fazer `push_back` do intervalo na lista do recurso, a lista `trial[r]` **já sai ordenada por início**. Não é preciso ordenar.
2. O **maior fim** já visto de uma máquina é sempre o fim do **último** intervalo dela processado até o momento. É por isso que um único valor por máquina (`lastEnd`) basta, e não precisamos guardar o máximo acumulado.

---

## 6. O que é `lastEnd` e para que serve

`lastEnd[j]` guarda, durante o sweep de um recurso, o **fim (estendido) do último intervalo já processado da máquina `j`**.

Ele responde, em $O(1)$, à pergunta: *"a máquina `j` ainda está ocupando este recurso no instante `s`?"*

$$
\text{máquina } j \text{ ainda está ocupada em } s \iff lastEnd[j] > s
$$

Como o sweep processa os intervalos em ordem crescente de início, quando chega um intervalo de início `s`, todos os intervalos que começaram antes já foram consumidos. Se o último intervalo de `j` ainda não terminou (`lastEnd[j] > s`), há sobreposição com o intervalo atual. Por causa da monotonicidade (seção 5), esse último intervalo é também o que termina mais tarde, então testar só ele é suficiente.

Valor inicial: `-∞` (a máquina ainda não apareceu para aquele recurso). Deve ser resetado a cada recurso visitado (só para as máquinas tocadas, ou com um carimbo por recurso).

---

## 7. O sweep, passo a passo

Seja `m` a rota candidata e `r` um recurso tocado por ela.

* Lista **A** = `trial[r]` (intervalos de `m`, ordenados).
* Lista **B** = `G[r]` **ignorando** as entradas com `k == m`.

Fazemos um merge de dois ponteiros, sempre consumindo o intervalo de menor `(start, k)`:

```
lastEnd[j] = -inf para as máquinas envolvidas
mask = 0                                   // M bits, local ao recurso

enquanto houver elementos em A ou B:
    x = menor (start, k) entre as cabeças de A e B

    se x vem de A (máquina m):
        para cada j != m com lastEnd[j] > x.start:    // outras máquinas ainda ocupadas
            mask |= (1 << j)
        lastEnd[m] = x.end
    senão (x vem de B, máquina k != m):
        se lastEnd[m] > x.start:                      // m ainda ocupada
            mask |= (1 << k)
        lastEnd[k] = x.end

V_trial += popcount(mask)
```

### Por que `mask`

`mask` marca **quais máquinas** conflitam com `m` naquele recurso. `popcount(mask)` dá o número de máquinas distintas, ou seja, o número de pares `(m, k)` violados. Isso preserva a semântica atual da FO (um par conta uma vez por recurso, mesmo com várias sobreposições).

### Por que o sweep é correto

Para dois intervalos `a` (de `m`) e `b` (de `k ≠ m`):

* Se `a.s <= b.s`: a sobreposição é detectada ao processar `b`, pois `lastEnd[m]` já reflete `a` (ou um intervalo posterior de `m` com início ainda anterior a `b.s` e fim maior).
* Se `b.s < a.s`: a sobreposição é detectada ao processar `a`, via `lastEnd[k]`.
* Empate de início: o segundo a ser processado enxerga o primeiro, pois todo intervalo é não vazio (`lastEnd > s`).
* Pares entre outras máquinas **não** são avaliados: não envolvem `m` e já estão contabilizados em `V_total`.

---

## 8. Fórmula da FO do candidato

$$
V_{novo} = V_{total} - V_{antigo}(m) + V_{trial}(m)
$$

* $V_{total}$: cache da solução corrente.
* $V_{antigo}(m)$: violações de `m` com as demais na solução corrente, calculadas **uma vez** ao entrar no laço externo da rota `m`.
* $V_{trial}(m)$: soma dos `popcount(mask)` de todos os recursos tocados pela rota candidata.

A FO final continua sendo:

$$
f = \text{(tardiness} + \varepsilon \cdot \text{completion)} + \text{nao\_alocados} \cdot W_{na} + V_{novo} \cdot P_{recurso}
$$

### Movimentos inter-rota ($m$ e $l$)

* Constroem-se `trial` de `m` e de `l`.
* As "outras" máquinas são `G[r]` sem `m` e sem `l`.
* O par $(m, l)$ é comparado entre os dois `trial`, e deve ser **contado uma única vez**.
* Subtrai-se $V_{antigo}(m) + V_{antigo}(l) - V_{antigo}(m,l)$ (sem duplicar o par $(m,l)$).

---

## 9. Atualização no commit (só quando melhora a solução)

Com best improvement, cada passada de vizinhança aplica **no máximo um** movimento. Para cada recurso tocado **antes ou depois** pela(s) rota(s) alterada(s):

1. **Filtrar** `G[r]`, removendo as entradas com `k == m` (e `k == l`). Preserva a ordem. $O(n_r)$.
2. **Pegar** `trial[r]` (já ordenado pela propriedade da seção 5).
3. **Fazer `merge`** de duas listas ordenadas (`std::merge` ou `inplace_merge`). $O(n_r)$.
4. $V_{total} \leftarrow V_{novo}$ (já calculado na avaliação; não é preciso recalcular).
5. Atualizar cache da rota (`cost`, `allocated_jobs`, `touched_resources`), como `evaluate()` já faz.

Recursos que a rota **deixou de tocar** também precisam ter suas entradas removidas de `G[r]`.

Custo do commit: $O\big(\sum_{r} n_r\big) \le O(n)$ por movimento aceito.

---

## 10. Exemplo completo

Dados: $M = 3$, `big_setup` = 60, recurso 7.

| Job | Máquina | start | end | Intervalo       |
| --- | -------- | ----- | --- | --------------- |
| B   | 1        | 50    | 70  | [50, 130)<br /> |
| A   | 0        | 100   | 130 | [100, 190)      |
| C   | 2        | 300   | 320 | [300, 380)      |

```
G[7] = [ (50,130,k=1), (100,190,k=0), (300,380,k=2) ]
```

A e B se sobrepõem (100 < 130 e 50 < 190). Suponha $V_{total} = 4$ e $V_{antigo}(0) = 1$ (só o recurso 7 contribui para a rota 0).

### Candidato 1: A atrasa para start 240, end 270

`trial[7] = [(240,330,k=0)]`. `G[7]` sem a máquina 0: `[(50,130,1), (300,380,2)]`.

| Passo | Consome            | O que faz                                                    | `lastEnd[0,1,2]` | `mask` |
| ----- | ------------------ | ------------------------------------------------------------ | ------------------ | -------- |
| 1     | (50,130,k=1) de B  | `lastEnd[0]=-∞ > 50`? Não                                | [-∞, 130, -∞]    | ∅       |
| 2     | (240,330,k=0) de A | outros:`lastEnd[1]=130>240`? não; `lastEnd[2]=-∞` não | [330, 130, -∞]    | ∅       |
| 3     | (300,380,k=2) de B | `lastEnd[0]=330 > 300`? Sim, marca bit 2                   | [330, 130, 380]    | {2}      |

$V_{trial} = 1 \Rightarrow V_{novo} = 4 - 1 + 1 = 4$. Sem melhora na penalidade de recurso.

### Candidato 2: A vai para start 400, end 430

`trial[7] = [(400,490,k=0)]`.

| Passo | Consome            | O que faz                                                  | `lastEnd[0,1,2]` | `mask` |
| ----- | ------------------ | ---------------------------------------------------------- | ------------------ | -------- |
| 1     | (50,130,k=1)       | `lastEnd[0]=-∞ > 50`? Não                              | [-∞, 130, -∞]    | ∅       |
| 2     | (300,380,k=2)      | `lastEnd[0]=-∞ > 300`? Não                             | [-∞, 130, 380]    | ∅       |
| 3     | (400,490,k=0) de A | `lastEnd[1]=130>400`? não; `lastEnd[2]=380>400`? não | [490, 130, 380]    | ∅       |

$V_{trial} = 0 \Rightarrow V_{novo} = 4 - 1 + 0 = 3$. Melhora. Se for o melhor da vizinhança, é aceito.

### Commit do candidato 2

1. Remove `k == 0` de `G[7]`: `[(50,130,1), (300,380,2)]`.
2. `trial[7] = [(400,490,0)]`.
3. Merge: `[(50,130,1), (300,380,2), (400,490,0)]`.
4. $V_{total} = 3$.

---

## 11. Complexidade

### Avaliação por candidato

| Etapa                                                    | Custo                          |
| -------------------------------------------------------- | ------------------------------ |
| Construir`trial[r]` no `computeRoute` (já ordenado) | $O(\lvert route \rvert)$     |
| Sweep em cada recurso`r` tocado                        | $O(a_r + b_r + a_r \cdot M)$ |
| Montar a FO com custos em cache das outras rotas         | $O(M)$                       |
| **Total**                                          | $O(n)$                       |

* $a_r$ = jobs do recurso `r` na rota candidata; $b_r$ = jobs de `r` nas outras rotas.
* $\sum_r (a_r + b_r) \le n$.
* O fator $M$ (checagem das outras máquinas ativas ao processar um intervalo de `m`) é constante da instância.
* Comparação **direta** por pares (sem sweep) custaria $O(a_r \cdot b_r)$, que no pior caso ($a_r = b_r = n/2$) é $O(n^2)$. O sweep garante $O(n)$.

### Commit por movimento aceito

$$
O\Big(\sum_{r \in touched} n_r\Big) \le O(n)
$$

### Por que o commit não pesa

Com best improvement há **um commit** por passada de vizinhança, contra milhares de avaliações (da ordem de $n^2$ candidatos nas vizinhanças inter-rota). O custo de manter `G[r]` ordenado é diluído.

### Comparação com o bitset atual

|                    | Custo por candidato (checagem de recurso)                        |
| ------------------ | ---------------------------------------------------------------- |
| Bitset atual       | $R \cdot \binom{M}{2} \cdot W \approx 21\,600$ (instância 60) |
| Intervalos + sweep | $O(\sum_r n_r)$, na prática dezenas de operações            |

---

## 12. Ciclo completo

```
entra na rota m  ->  calcula V_antigo(m)                         O(sum n_r)    1x por rota
para cada candidato:
    constrói trial (ordenado pela rota)                          O(|route|)
    sweep com G[r] sem m, usando lastEnd e mask                  O(sum n_r)
    V_novo = V_total - V_antigo + V_trial                        O(1)
    FO = custo das rotas + penalidades                           O(M)
fim do laço, se houve melhora:
    commit: filtra + merge em G[r], V_total = V_novo             O(sum n_r)    1x por passada
```

---

## 13. Pontos de atenção na implementação

1. **Truncamento no horizonte:** usar `min(H + 1, end + big_setup)`, idêntico ao `set_range`, para a FO não divergir da atual.
2. **Intervalos semiabertos:** a comparação deve ser `a.s < b.e && b.s < a.e`, igual ao bitset.
3. **Desempate determinístico:** ordenar `G[r]` por `(start, k)`.
4. **Reset de `lastEnd`:** apenas nas máquinas que aparecem em `G[r]` (ou carimbo por recurso), para não pagar $O(M)$ por recurso visitado.
5. **Pool virtual (jobs não processados):** a rota de índice `M` (a rota `M + 1`, `m >= count_machines`) guarda os jobs não processados. Ela não possui recursos, não entra em `G[r]`, não tem `V_antigo` nem `trial`. Em movimentos que envolvem essa rota, ela é tratada como "sem máquina" na varredura (sem conflito possível).
6. **Evitar alocações por candidato:** `trial` e as máscaras devem ser buffers reutilizados (`clear()` apenas nas entradas tocadas, como o `clearTrialBuffer` faz hoje).
7. **Distribuição de jobs por recurso:** se algum recurso concentrar muitos jobs, o fator $a_r \cdot M$ e o merge crescem. Vale conferir a distribuição nas instâncias antes de adotar.

---

## 14. Validação sugerida (antes de substituir o bitset)

1. Gerar muitas soluções aleatórias (e soluções pós-movimento) e comparar **o número de violações** da versão nova com `countResourceViolations` atual. Devem ser **idênticos**.
2. Comparar a FO final da heurística (mesma semente) entre as duas versões.
3. Rodar `make` em `src/heuristics/` e `pytest` na raiz do repositório.
4. Medir tempo na instância `data/trusted/05112025/60/input.json` para confirmar o ganho (perfilar com `perf` ou `gprof` antes e depois).
