# Movimentos de Busca Local — Sequenciamento em Máquina Única

Todos os movimentos operam sobre uma sequência com **jobs dummy** nas pontas (posições `0` e `n-1`).
Os dummies nunca são movidos. Jobs reais ocupam as posições `1 .. n-2`.

A função objetivo avaliada é:

```
FO = sum_tardiness + W × jobs_não_alocados + ε × sum_completion_time
```

onde `W = n×H + 1` e `ε = 1/W`.

---

## Movimentos Intra-Rota

Operam dentro da sequência de **uma única máquina**.

---

### Swap

Troca dois jobs de posição na sequência.

**Exemplo** — i=2, j=4:
```
Antes:  [D, 1, 2, 3, 4, 5, D]
Depois: [D, 1, 4, 3, 2, 5, D]
```

**Propriedades:**
- **Simétrico**: trocar (i, j) dá o mesmo resultado que trocar (j, i) → `j` começa em `i+1`
- **Complexidade de avaliação**: O(1) swap + desfaz; nenhuma realocação de vetor
- **Quando ajuda**: jobs com release dates muito diferentes trocam de posição, reduzindo esperas

**Intervalos:**
```
i ∈ [1, n-2]
j ∈ [i+1, n-2]
```

---

### OrOpt-k (Reinserção de segmento)

Remove um bloco de `k` jobs consecutivos da posição `i` e o reinsere na posição `j` do vetor pós-remoção, mantendo a ordem interna do segmento.

#### OrOpt-1 (Reinserção simples)

**Exemplo** — i=2, j=5:
```
Antes:  [D, 1, 2, 3, 4, 5, 6, D]
Remove job 2:   [D, 1, 3, 4, 5, 6, D]
Insere em j=5:  [D, 1, 3, 4, 5, 2, 6, D]
```

#### OrOpt-2

**Exemplo** — i=2, j=5:
```
Antes:  [D, 1, 2, 3, 4, 5, 6, D]
Remove {2,3}:      [D, 1, 4, 5, 6, D]
Insere {2,3} em 5: [D, 1, 4, 5, 2, 3, 6, D]
```

#### OrOpt-3

**Exemplo** — i=1, j=4:
```
Antes:  [D, 1, 2, 3, 4, 5, 6, D]
Remove {1,2,3}:      [D, 4, 5, 6, D]
Insere {1,2,3} em 4: [D, 4, 5, 6, 1, 2, 3, D]
```

**Propriedades:**
- **Assimétrico**: mover para frente e para trás produz resultados distintos → `j` percorre todo o intervalo válido
- **j = i é no-op** (reinserção no mesmo lugar) → pulado
- **Quando ajuda**: um bloco de jobs afins (mesmo resource_id) pode ter setup menor em outro ponto da sequência

**Intervalos (no vetor pós-remoção de tamanho n-k):**
```
i ∈ [1, n-1-k]
j ∈ [1, n-k-1],  j ≠ i
```

---

### 2-Opt

Inverte o segmento `]i, j]` (posições `i+1` até `j` inclusive), equivalente a desfazer dois "cruzamentos" na sequência.

**Exemplo** — i=2, j=5 em sequência de 8 elementos:
```
Antes:  [D, 1, 2, | 3, 4, 5 |, 6, D]
Depois: [D, 1, 2, | 5, 4, 3 |, 6, D]
```

O job na posição `i` não é movido; apenas o interior `]i, j]` é revertido.

**Propriedades:**
- **Simétrico**: reverter `]i,j]` e reverter `]j,i]` são equivalentes → `j` começa em `i+2` (`j=i+1` reverteria segmento de tamanho 1, no-op)
- **Quando ajuda**: sequências com inversões de ordem em relação aos due dates; especialmente efetivo em subproblemas com estrutura de TSP

**Intervalos:**
```
i ∈ [1, n-3]
j ∈ [i+2, n-2]
```

---

## Movimentos Inter-Rota

Operam entre **duas máquinas distintas** (A e B). Requerem que o job movido seja compatível com a máquina de destino (setup, resource_id, horizonte H).

---

### Realocate (Reinserção entre rotas)

Remove um job da posição `i` da máquina A e insere na posição `j` da máquina B.

**Exemplo** — remove job `a3` de A, insere entre `b2` e `b3` em B:
```
Antes:
  A: [D, a1, a2, a3, a4, D]
  B: [D, b1, b2, b3, D]

Depois:
  A: [D, a1, a2, a4, D]
  B: [D, b1, b2, a3, b3, D]
```

**Função objetivo:** avalia A' e B' separadamente e soma; melhora se `FO(A') + FO(B') < FO(A) + FO(B)`.

**Propriedades:**
- **Assimétrico**: mover de A→B é diferente de mover de B→A
- **Restrição de viabilidade**: o job `a3` deve ser compatível com a máquina B (capacidade, resource_id, setup disponível em B)
- **Quando ajuda**: máquinas com carga desequilibrada; um job atrasado em A pode ser alocado antes do due date em B

**Intervalos:**
```
i ∈ [1, |A|-2]         (jobs reais de A)
j ∈ [1, |B|-1]         (posições de inserção em B, pós-remoção não se aplica aqui)
```

---

### Swap Inter-Rota

Troca um job `a_i` de A com um job `b_j` de B, mantendo cada job na mesma posição relativa dentro da rota da outra máquina.

**Exemplo** — troca `a2` ↔ `b2`:
```
Antes:
  A: [D, a1, a2, a3, D]
  B: [D, b1, b2, b3, D]

Depois:
  A: [D, a1, b2, a3, D]
  B: [D, b1, a2, b3, D]
```

**Propriedades:**
- **Simétrico**: trocar (a_i, b_j) e (b_j, a_i) é equivalente
- **Restrição de viabilidade dupla**: `a_i` deve ser compatível com B e `b_j` com A
- **Quando ajuda**: dois jobs com due dates conflitantes nas suas máquinas originais podem ser aliviados trocando de ambiente; também equilibra carga se os processing_slots diferirem

**Intervalos:**
```
i ∈ [1, |A|-2]
j ∈ [1, |B|-2]
```

---

## VNS — Ordem de Exploração

O algoritmo `LocalSearch::algorithm()` implementa **Variable Neighborhood Search**: sorteia uma vizinhança da lista `NL`, aplica *best-improvement*, e:

| Resultado | Ação |
|-----------|------|
| Melhora   | Reseta `NL = {1,2,3,4,5}` (recomeça do início) |
| Sem melhora | Remove a vizinhança de `NL` em O(1) |

Termina quando `NL` fica vazia — ótimo local simultâneo em todas as vizinhanças.

| ID | Vizinhança |
|----|------------|
| 1  | Swap       |
| 2  | OrOpt-1    |
| 3  | 2-Opt      |
| 4  | OrOpt-2    |
| 5  | OrOpt-3    |

Os movimentos inter-rota (Realocate, Swap inter-rota) são candidatos a vizinhanças 6 e 7 caso o modelo seja estendido para múltiplas máquinas simultâneas.
