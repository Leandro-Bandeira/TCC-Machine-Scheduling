#pragma once

#include <vector>
#include "../models/ProblemData.hpp"
#include "../models/solution.hpp"
#include "../utils/objective.hpp"

// Implementa a fase de busca local via RVND (Random Variable Neighborhood Descent).
//
// Movimentos intra-rota (vizinhanças 1-5):
//   Swap    — troca dois jobs de posição dentro de uma rota
//   OrOpt-k — reinsere um segmento de k jobs consecutivos em outra posição da mesma rota
//   2-Opt   — inverte um segmento de uma rota entre as posições i+1 e j
//
// Movimentos inter-rota (vizinhanças 6-7):
//   SwapInterRoute — troca job_i da rota m com job_j da rota l (m < l), simétrico
//   Realocate      — remove job_i da rota m e insere na posição j da rota l (m ≠ l), assimétrico
//
// Todos os movimentos avaliam a FO sobre a solução completa (todas as rotas).
// Violações de big_setup cross-rota são penalizadas dentro de evaluate.
//
// O método algorithm() implementa o RVND: sorteia aleatoriamente uma vizinhança de NL,
// aplica best-improvement (descida), e reseta NL se houve melhora (voltando a explorar
// todas as vizinhanças). Se não houve melhora, remove a vizinhança de NL em O(1).
// Termina quando NL fica vazia: ótimo local simultâneo em todas as vizinhanças.
class LocalSearch{
    public:
        static bool bestImprovementSwap(const ProblemData& problemData, Solution& solution);
        static bool bestImprovementOrOpt(const ProblemData& problemData, Solution& solution, int k);
        static bool bestImprovement2Opt(const ProblemData& problemData, Solution& solution);
        static void algorithm(const ProblemData& problemData, Solution& solution);
        static bool bestImprovementSwapInterRoute(const ProblemData& problemData, Solution& solution);
        static bool bestImprovementRealocate(const ProblemData& problemData, Solution& solution);
};
