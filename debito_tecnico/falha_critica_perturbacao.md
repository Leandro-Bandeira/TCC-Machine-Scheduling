# Débito Técnico: Falha Crítica no Operador de Perturbação Monomáquina

**Arquivo afetado**: [`src/heuristics/algorithms/ils.cpp`](file:///home/leandro-bandeira/Documents/me/TCC/TCC-Machine-Scheduling/src/heuristics/algorithms/ils.cpp)  
**Método**: `Solution ILS::perturbation(Solution solution)`  
**Severidade**: Alta  
**Status**: Identificado / Pendente de Correção  

---

## 1. Descrição do Problema

O operador de perturbação para instâncias com uma única máquina (`count_routes == 1`) implementa o movimento **$(l, l')$-Block Swap Intra-Máquina**, que sorteia dois blocos disjuntos de jobs $A$ (tamanho $l$) e $B$ (tamanho $l'$) e troca suas posições na sequência.

O trecho de código correspondente em `src/heuristics/algorithms/ils.cpp` (linhas 103–137) é:

```cpp
int lower = 2;
std::vector<Job>& current_route = solution.routes[0];

// N = jobs reais, sem contar os dois dummies (início e fim da rota)
int N = (int)current_route.size() - 2;
int upper = N / 4;

// rota curta demais pra caber dois blocos de tamanho >= 2 cada
if (upper >= 2) {
    int l  = lower + std::rand() % (upper - lower + 1); // tamanho do bloco A, [2, N/4]
    int lp = lower + std::rand() % (upper - lower + 1); // tamanho do bloco B, [2, N/4]

    // índices reais válidos: 1..N (0 e size-1 são os dummies)
    int i = 1 + std::rand() % (N - l + 1);  // início do bloco A
    int j_min = i + l;                      // B só pode começar depois do fim de A (sem overlap)
    int j_max = N - lp + 1;                 // B precisa caber até o fim da rota

    // não há espaço pra encaixar B depois de A com esse (l, l') sorteado
    if (j_min <= j_max) {
        int j = j_min + std::rand() % (j_max - j_min + 1); // início do bloco B
        ...
        current_route = new_route;
        solution.invalidateRoute(0);
    }
}
```

Duas condições provocam a falha silenciosa da perturbação:

### Condição A: Instâncias pequenas ($N < 8$)
* Para instâncias onde a máquina possui menos de 8 jobs reais ($N \in [1, 7]$):
  $$\text{upper} = \lfloor N / 4 \rfloor < 2$$
* Como o código exige `if (upper >= 2)`, o bloco condicional inteiro é ignorado.
* **Resultado**: Para qualquer instância com $N < 8$, a perturbação não executa nenhuma alteração na rota e retorna a solução intacta.

### Condição B: Sorteio inviável de posições ($j_{\min} > j_{\max}$) mesmo com $N \ge 8$
* Para que dois blocos de tamanhos $l$ e $l'$ caibam em sequência sem sobreposição, é necessário que:
  $$j_{\min} = i + l \le N - lp + 1 = j_{\max}$$
* O índice $i$ é sorteado aleatoriamente em $[1, N - l + 1]$. Se $i$ for sorteado próximo do final da rota, $j_{\min} > j_{\max}$.
* Como o código testa `if (j_min <= j_max)` sem nenhuma tentativa adicional ou ajuste de limites, a troca é descartada.
* **Resultado**: A rota permanece inalterada de forma silenciosa.

---

## 2. Impacto no Desempenho do ILS

Quando a perturbação falha:
1. `ILS::perturbation` retorna a mesma solução `best` sem nenhuma modificação.
2. Na iteração seguinte do laço `while (iterILS <= m_maxIterILS)`, a função `LocalSearch::algorithm` é chamada com uma solução que **já é um ótimo local** em relação a todas as 7 vizinhanças do RVND.
3. O RVND testa exaustivamente todos os vizinhos em todas as vizinhanças, não encontra nenhuma melhora e retorna a solução idêntica.
4. Nenhuma exploração de novos vales/bacias de atração ocorre até que `iterILS` atinja `m_maxIterILS`.
5. **Conclusão**: O ILS degenera para uma busca puramente aleatória por reinício (equivalente a rodar apenas o construtivo GRASP $50$ vezes, com o loop interno do ILS totalmente inoperante).

---

## 3. Plano de Remediação

Para solucionar o débito técnico, recomenda-se:

1. **Adicionar Mecanismo de Fallback para $N < 8$**:
   * Se $N \ge 4$, permitir blocos de tamanho mínimo $l = 1, l' = 1$ ou $l=2, l'=1$.
   * Se $N < 4$, realizar um swap simples de duas posições aleatórias distintas $i \ne j$ ($1 \le i < j \le N$).

2. **Garantir Sorteio Válido para $N \ge 8$**:
   * Restringir o sorteio do início do bloco $A$ para que sempre haja espaço para o bloco $B$:
     $$i \in [1, \; N - l - lp + 1]$$
     Dessa forma, $j_{\min} = i + l \le N - lp + 1 = j_{\max}$ é **sempre garantido por construção matemática**, eliminando a necessidade de sorteios rejeitados.

3. **Validação de Não-Identidade**:
   * Garantir que a solução resultante da perturbação seja estritamente diferente da solução de entrada antes de retornar.
