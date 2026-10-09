# Abordagem de Máquina Virtual de Pool para Gestão de Jobs Não Alocados

Este documento detalha a arquitetura e o funcionamento da **Máquina Virtual de Pool** para gerenciar a entrada e saída de tarefas não alocadas (*unallocated jobs*) na meta-heurística ILS/RVND.

---

## 1. Motivação e Conceito

Em problemas de escalonamento onde tarefas podem ser deixadas de fora (ou quando o estouro do horizonte de planejamento penaliza a não alocação), a busca local e a perturbação precisam de mecanismos para:
1. **Desalocar (Remover)** tarefas de uma máquina quando elas causam custos excessivos de atraso (*tardiness*) ou setup.
2. **Re-alocar (Re-inserir)** tarefas que estavam no pool de volta para máquinas reais quando houver capacidade disponível.
3. **Substituir (Swap)** diretamente um job ativo por um não alocado em um único passo de busca local.

Em vez de criar vizinhanças dedicadas adicionais (como `DropJob` e `AddJob`) ou modificar a estrutura física das rotas com elementos pós-dummy, adicionamos uma **Máquina Virtual de Pool** (`routes[count_machines]`).

---

## 2. Representação na Estrutura de Dados (`Solution`)

Para uma instância com $m$ máquinas reais ($0, \dots, m-1$), a solução passa a gerenciar $m+1$ rotas:

$$\text{Solution.routes} = [\text{Rota Máquina 0}, \; \text{Rota Máquina 1}, \; \dots, \; \text{Rota Máquina } m-1, \; \mathbf{\text{Rota Pool Virtual (Máquina } m)}]$$

* **Máquinas Reais ($0 \dots m-1$)**:
  $$\text{Rota}_k = [0, \; J_1, \; J_2, \; \dots, \; J_p, \; 0]$$
  *(Calculam tempo de processamento, setup, tardiness e conclusão normalmente).*

* **Máquina Virtual de Pool ($m$)**:
  $$\text{Rota}_{\text{pool}} = [0, \; J_{u1}, \; J_{u2}, \; \dots, \; J_{uq}, \; 0]$$
  *(Não calcula tempos nem setups; todos os jobs contidos aqui pagam a penalidade `weight_not_allocated`).*

---

## 3. Impacto e Reuso nas Vizinhanças RVND

Com essa estrutura, os movimentos inter-máquinas padrão **já existentes** cobrem 100% das operações de alocação/desalocação sem nenhuma necessidade de novos métodos de busca local:

1. **Desalocação (`bestImprovementRealocate`)**:
   * Mover um job da Máquina Real $k \rightarrow$ Máquina do Pool.
2. **Re-alocação (`bestImprovementRealocate`)**:
   * Mover um job da Máquina do Pool $\rightarrow$ Máquina Real $k$.
3. **Substituição Direta (`bestImprovementSwapInterRoute`)**:
   * Trocar um job da Máquina Real $k$ com um job da Máquina do Pool.
4. **Perturbação ILS**:
   * Sorteia movimentações aleatórias entre máquinas reais e a máquina do pool, promovendo diversificação efetiva ao forçar a reativação ou desalocação de tarefas.

---

## 4. Avaliação na Função Objetivo (`objective.cpp`)

Ao avaliar a rota da Máquina Virtual de Pool ($m$):
* Tempos de processamento e setups não são calculados.
* A quantidade de jobs alocados na Máquina do Pool não incrementa o contador de jobs alocados.
* A função `evaluate()` atribui `weight_not_allocated` para cada job presente na rota do pool.

---

## 5. Pós-Processamento e Exportação

Durante a serialização dos resultados finais, a rota virtual `routes[m]` é ignorada na geração das rotas por máquina no output final, garantindo compatibilidade total com o pipeline.
