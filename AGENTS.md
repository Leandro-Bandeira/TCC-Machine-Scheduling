# AGENTS.md - Diretrizes de Agentes para o Projeto TCC-Machine-Scheduling

Este arquivo estabelece regras estritas de consulta e comportamento para assistentes de IA e subagentes trabalhando neste repositório.

---

## ⚠️ Regras Obrigatórias de Leitura

### **Consultas sobre Heurísticas (ILS, RVND, Movimentos, Busca Local)**

Sempre que a solicitação do usuário ou a tarefa do agente envolver **heurísticas**, **busca local**, **ILS**, **GRASP**, **RVND** ou **movimentos de vizinhança** (seja para explicar, modificar, depurar ou implementar código em C++ ou Python), o agente **DEVE OBRIGATORIAMENTE LER OS SEGUINTES DOIS ARQUIVOS** usando a ferramenta `view_file` antes de responder ou alterar código:

1. [`heuristics_information/ils_explication.md`](file:///home/leandro-bandeira/Documents/me/TCC/TCC-Machine-Scheduling/heuristics_information/ils_explication.md)
   * *Contém a fundamentação teórica do ILS, fluxo do GRASP, critérios de perturbação e parâmetros do kit.*
2. [`heuristics_information/moviments.md`](file:///home/leandro-bandeira/Documents/me/TCC/TCC-Machine-Scheduling/heuristics_information/moviments.md)
   * *Contém a especificação exata das 7 vizinhanças RVND (intra e inter-rota) e movimentos de perturbação implementados no código C++ (`src/heuristics/`).*

---

## 📋 Diretrizes Gerais do Repositório

1. **Preservação do Modelo de Otimização (`src/main/optimize.py`)**:
   - Respeitar a função objetivo MIP Time-Index: minimização de *total tardiness*, penalidade por não alocação e desempate por *completion time*.

2. **Manutenção do Código C++ (`src/heuristics/`)**:
   - Manter compatibilidade com o padrão **C++17**.
   - Garantir sincronia entre a leitura de `input.json` e a estrutura de dados `ProblemData.hpp`.
   - Sempre validar compilação executando `make` no diretório `src/heuristics/`.

3. **Validação de Testes**:
   - Executar `pytest` após qualquer modificação no pipeline para garantir que nenhum job seja duplicado ou omitido.
