#pragma once

#include <vector>
#include "../models/ProblemData.hpp"
#include "../models/solution.hpp"
#include "../utils/objective.hpp"

// Implementa a fase de busca local via VNS (Variable Neighborhood Search).
//
// Três famílias de movimentos são exploradas como vizinhanças distintas:
//   Swap    — troca dois jobs de posição na sequência
//   OrOpt-k — reinsere um segmento de k jobs consecutivos em outra posição
//   2-Opt   — inverte um segmento da sequência entre as posições i+1 e j
//
// O método algorithm() implementa o VNS: sorteia uma vizinhança da lista NL,
// aplica best-improvement, e reseta NL se houve melhora (voltando a explorar
// todas as vizinhanças). Se não houve melhora, remove a vizinhança de NL.
// Termina quando NL fica vazia (nenhuma vizinhança melhora a solução).
class LocalSearch{
    public:
        static bool bestImprovementSwap(const ProblemData& problemData, Solution& solution);
        static bool bestImprovementOrOpt(const ProblemData& problemData, Solution& solution, int k);
        static bool bestImprovement2Opt(const ProblemData& problemData, Solution& solution);
        static void algorithm(const ProblemData& problemData, Solution& solution);
};
