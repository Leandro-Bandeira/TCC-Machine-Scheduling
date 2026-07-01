#pragma once
#include "../models/ProblemData.hpp"
#include "../models/solution.hpp"

// Iterated Local Search (ILS) para o problema de sequenciamento em máquina única.
//
// Fluxo principal:
//   1. construction() — gera solução inicial via GRASP
//   2. algorithm()    — chama construction() e aplica busca local (VNS)
//
// A solução é mantida como membro para evitar cópias desnecessárias entre fases.
class ILS{
    public:
        ILS(const ProblemData& problem_data)
        :problem_data(problem_data) {}

        // Constrói solução inicial usando GRASP: agrupa jobs por release_date,
        // ordena por setup crescente em relação ao último job inserido,
        // e seleciona aleatoriamente dentro de uma lista restrita de candidatos (RCL).
        void construction();

        // Executa o algoritmo completo: construção + busca local VNS.
        void algorithm();

    private:
        const ProblemData& problem_data; // dados da instância (somente leitura)
        Solution solution;               // solução corrente, modificada in-place pelas fases
};
