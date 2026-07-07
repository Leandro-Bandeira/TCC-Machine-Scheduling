#include "LocalSearch.hpp"
#include <algorithm>
#include <iomanip>
#include <random>
#include <iostream>

#include "../utils/objective.hpp"
#include "../utils/utils.hpp"

// ---------------------------------------------------------------------------
// 2-Opt
// ---------------------------------------------------------------------------
//
// Dado um par de posições (i, j) com j >= i+2, inverte o segmento ]i, j]:
//
//   Antes:  ... | seq[i] | seq[i+1] ... seq[j] | seq[j+1] | ...
//   Depois: ... | seq[i] | seq[j]   ... seq[i+1] | seq[j+1] | ...
//
// Exemplo para i=2, j=5 em sequência [0,1,2,3,4,5,6,7]:
//   Inverte posições 3,4,5 → [0,1,2,5,4,3,6,7]
//
// O movimento é simétrico: inverter ]i,j] dá o mesmo resultado que inverter ]j,i]
// portanto j sempre começa em i+2 (j=i+1 seria inversão de segmento de tamanho 1, no-op).
// Os dummies nas pontas (posições 0 e size-1) nunca são movidos.
bool LocalSearch::bestImprovement2Opt(const ProblemData &problemData, Solution &solution){
    double bestDelta = solution.objective_function;
    int best_route = -1, best_i = -1, best_j = -1;

    for (int m = 0; m < (int)solution.routes.size(); m++) {
        std::vector<Job> route = solution.routes[m];

        for (size_t i = 1; i < route.size() - 1; i++) {
            for (size_t j = i + 2; j < route.size() - 1; j++) {
                std::reverse(route.begin() + i + 1, route.begin() + j + 1);

                Solution temp = solution;
                temp.routes[m] = route;
                double delta = evaluate(temp, problemData);
                if (delta < bestDelta) {
                    bestDelta = delta;
                    best_route = m;
                    best_i = i;
                    best_j = j;
                }
                std::reverse(route.begin() + i + 1, route.begin() + j + 1); // desfaz
            }
        }
    }

    if (best_route != -1) {
        std::reverse(solution.routes[best_route].begin() + best_i + 1,
                     solution.routes[best_route].begin() + best_j + 1);
        solution.objective_function = bestDelta;
        return true;
    }
    return false;
}

// ---------------------------------------------------------------------------
// OrOpt-k (Reinserção de segmento)
// ---------------------------------------------------------------------------
//
// Remove um bloco de k jobs consecutivos da posição i e o reinsere na posição j
// do vetor pós-remoção. k pode ser 1, 2 ou 3.
//
// Exemplo para k=1, i=2, j=5 em [D,1,2,3,4,5,6,D]:
//   Remove job na posição 2 → [D,1,3,4,5,6,D]
//   Insere na posição 5     → [D,1,3,4,5,2,6,D]
//
// Exemplo para k=2, i=2, j=4 em [D,1,2,3,4,5,6,D]:
//   Remove jobs nas posições 2,3 → [D,1,4,5,6,D]
//   Insere {2,3} na posição 4   → [D,1,4,5,2,3,6,D]   (mantém ordem interna do segmento)
//
// Diferente do Swap e 2-Opt (simétricos), o OrOpt é assimétrico: mover o segmento
// para frente e para trás produz resultados distintos, por isso j percorre todo o
// intervalo válido [1, n-k-1] no vetor pós-remoção (pulando j==i, que seria no-op).
// Os dummies nas pontas nunca são movidos.
bool LocalSearch::bestImprovementOrOpt(const ProblemData &problemData, Solution &solution, int k){
    double bestDelta = solution.objective_function;
    int best_route = -1, best_i = -1, best_j = -1;

    for (int m = 0; m < (int)solution.routes.size(); m++) {
        const std::vector<Job>& route = solution.routes[m];
        int n = (int)route.size();

        for (int i = 1; i <= n - 1 - k; i++) {
            std::vector<Job> segment(route.begin() + i, route.begin() + i + k);

            for (int j = 1; j <= n - k - 1; j++) {
                if (j == i) continue;

                std::vector<Job> temp_route = route;
                temp_route.erase(temp_route.begin() + i, temp_route.begin() + i + k);
                temp_route.insert(temp_route.begin() + j, segment.begin(), segment.end());

                Solution temp = solution;
                temp.routes[m] = temp_route;
                double delta = evaluate(temp, problemData);
                if (delta < bestDelta) {
                    bestDelta = delta;
                    best_route = m;
                    best_i = i;
                    best_j = j;
                }
            }
        }
    }

    if (best_route != -1) {
        std::vector<Job> segment(solution.routes[best_route].begin() + best_i,
                                 solution.routes[best_route].begin() + best_i + k);
        solution.routes[best_route].erase(solution.routes[best_route].begin() + best_i,
                                          solution.routes[best_route].begin() + best_i + k);
        solution.routes[best_route].insert(solution.routes[best_route].begin() + best_j,
                                           segment.begin(), segment.end());
        solution.objective_function = bestDelta;
        return true;
    }
    return false;
}

// ---------------------------------------------------------------------------
// Swap
// ---------------------------------------------------------------------------
//
// Troca dois jobs de posição na sequência. É simétrico: trocar (i,j) dá o
// mesmo resultado que trocar (j,i), por isso j sempre começa em i+1.
//
// Exemplo para i=2, j=4 em [D,1,2,3,4,5,D]:
//   Troca posições 2 e 4 → [D,1,4,3,2,5,D]
//
// Os dummies nas pontas (posições 0 e size-1) nunca participam da troca.
// O swap é feito in-place sobre a cópia da rota e desfeito após avaliar,
// evitando realocar um vetor temporário a cada iteração.
bool LocalSearch::bestImprovementSwap(const ProblemData &problemData, Solution &solution){
    double bestDelta = solution.objective_function;
    int best_route = -1, best_i = -1, best_j = -1;

    for (int m = 0; m < (int)solution.routes.size(); m++) {
        std::vector<Job> route = solution.routes[m];

        for (size_t i = 1; i < route.size() - 1; i++) {
            for (size_t j = i + 1; j < route.size() - 1; j++) {
                std::swap(route[i], route[j]);

                Solution temp = solution;
                temp.routes[m] = route;
                double delta = evaluate(temp, problemData);
                if (delta < bestDelta) {
                    bestDelta = delta;
                    best_route = m;
                    best_i = i;
                    best_j = j;
                }
                std::swap(route[i], route[j]); // desfaz
            }
        }
    }

    if (best_route != -1) {
        std::swap(solution.routes[best_route][best_i], solution.routes[best_route][best_j]);
        solution.objective_function = bestDelta;
        return true;
    }
    return false;
}


// ---------------------------------------------------------------------------
// Swap Inter-Rota
// ---------------------------------------------------------------------------
//
// Troca job_i da rota m com job_j da rota l (m < l), mantendo cada job na
// mesma posição relativa dentro da rota de destino.
//
// Exemplo — troca rota[0][i=2] ↔ rota[1][j=1]:
//   Antes:
//     rota[0]: [D, a1, a2, a3, D]
//     rota[1]: [D, b1, b2, D]
//   Depois:
//     rota[0]: [D, a1, b1, a3, D]
//     rota[1]: [D, a2, b2, D]
//
// O movimento é simétrico: trocar (m,i,l,j) = trocar (l,j,m,i) → l começa em m+1.
// A FO é avaliada sobre a solução completa (ambas as rotas modificadas + demais inalteradas).
// O big_setup cross-rota é verificado dentro de evaluate — se violado, FO sobe e o
// movimento é descartado naturalmente.
// Os dummies nas pontas nunca são movidos: i e j partem de 1.
bool LocalSearch::bestImprovementSwapInterRoute(const ProblemData &problemData, Solution &solution){
    double bestDelta = solution.objective_function;
    int best_route_m = -1, best_route_l = -1, best_i = -1, best_j = -1;

    for(int m = 0; m < (int)solution.routes.size() - 1; m++){
        std::vector<Job> route_m = solution.routes[m];
        for(int l = m + 1; l < (int)solution.routes.size(); l++){
            std::vector<Job> route_l = solution.routes[l];
            for(int i = 1; i < (int)route_m.size() - 1; i++){
                for(int j = 1; j < (int)route_l.size() - 1; j++){
                    std::swap(route_m[i], route_l[j]); // Troca entre rotas
                    Solution temp = solution;
                    temp.routes[m] = route_m;
                    temp.routes[l] = route_l;
                    double delta = evaluate(temp, problemData);

                    if(delta < bestDelta){
                        bestDelta = delta;
                        best_route_m = m;
                        best_route_l = l;
                        best_i = i;
                        best_j = j;
                    }
                    std::swap(route_m[i], route_l[j]); // Desfaz a troca
                }
            }
        }
    }
    if(best_route_m != -1){
        std::swap(solution.routes[best_route_m][best_i], solution.routes[best_route_l][best_j]);
        solution.objective_function = bestDelta;
        return true;
    }
    return false;
}

// ---------------------------------------------------------------------------
// Realocate Inter-Rota
// ---------------------------------------------------------------------------
//
// Remove job_i da rota m e o insere na posição j da rota l (m ≠ l).
//
// Exemplo — move rota[0][i=2] para rota[1][j=1]:
//   Antes:
//     rota[0]: [D, a1, a2, a3, D]
//     rota[1]: [D, b1, b2, D]
//   Depois:
//     rota[0]: [D, a1, a3, D]
//     rota[1]: [D, a2, b1, b2, D]
//
// O movimento é assimétrico: mover (m→l) ≠ mover (l→m) → itera todos os pares m≠l.
// j varia de 1 até route_l.size()-1 inclusive: posições válidas antes do dummy final.
// Para cada job i, temp_m é construído fora do loop j (erase feito uma vez só).
// A FO é avaliada sobre a solução completa (ambas as rotas modificadas + demais inalteradas).
// O big_setup cross-rota é verificado dentro de evaluate — se violado, FO sobe e o
// movimento é descartado naturalmente.
bool LocalSearch::bestImprovementRealocate(const ProblemData &problemData, Solution &solution){
    double bestDelta = solution.objective_function;
    int best_route_m = -1, best_route_l = -1, best_i = -1, best_j = -1;
    for(int m = 0; m < (int)solution.routes.size(); m++){
        const std::vector<Job>& route_m = solution.routes[m];
        for(int l = 0; l < (int)solution.routes.size(); l++){
            if(m==l) continue;

            const std::vector<Job>&route_l = solution.routes[l];
            for(int i = 1; i < (int)route_m.size() - 1; i++){
                std::vector<Job> temp_m = route_m;
                Job job = temp_m[i];
                temp_m.erase(temp_m.begin() + i);
                for(int j = 1; j <= (int)route_l.size() - 1; j++){

                    std::vector<Job> temp_l = route_l;
                    temp_l.insert(temp_l.begin() + j, job);

                    Solution temp = solution;
                    temp.routes[m] = temp_m;
                    temp.routes[l] = temp_l;

                    double delta = evaluate(temp, problemData);

                    if (delta < bestDelta){
                        bestDelta = delta;
                        best_route_m = m;
                        best_route_l = l;
                        best_i = i;
                        best_j = j;
                    }
                }
            }
        }
    }

    if (best_route_m != -1){
        Job job = solution.routes[best_route_m][best_i];
        solution.routes[best_route_m].erase(solution.routes[best_route_m].begin() + best_i);
        solution.routes[best_route_l].insert(solution.routes[best_route_l].begin() + best_j, job);
        solution.objective_function = bestDelta;
        return true;
    }
    return false;
}
// ---------------------------------------------------------------------------
// RVND — Random Variable Neighborhood Descent
// ---------------------------------------------------------------------------
//
// Explora 7 vizinhanças em ordem aleatória:
//   1 = Swap        2 = OrOpt-1      3 = 2-Opt
//   4 = OrOpt-2     5 = OrOpt-3      6 = SwapInterRoute   7 = Realocate
//
// Regra de atualização:
//   - Sorteia vizinhança aleatória de NL
//   - Aplica best-improvement (descida): avalia todos os movimentos da vizinhança,
//     aplica o melhor se melhora a FO → reseta NL (volta a explorar todas)
//   - Se não melhorou → remove vizinhança de NL em O(1) via swap+pop_back
// Termina quando NL fica vazia: ótimo local simultâneo em todas as vizinhanças.
Solution LocalSearch::algorithm(const ProblemData &problemData, Solution solution){
    std::vector<int> NL = {1, 2, 3, 4, 5, 6, 7};
    bool improved = false;

    while(!NL.empty()){
        int n = std::rand() % NL.size();
        switch(NL[n]){
            case 1: improved = bestImprovementSwap(problemData, solution);              break;
            case 2: improved = bestImprovementOrOpt(problemData, solution, 1);          break;
            case 3: improved = bestImprovement2Opt(problemData, solution);              break;
            case 4: improved = bestImprovementOrOpt(problemData, solution, 2);          break;
            case 5: improved = bestImprovementOrOpt(problemData, solution, 3);          break;
            case 6: improved = bestImprovementSwapInterRoute(problemData, solution);    break;
            case 7: improved = bestImprovementRealocate(problemData, solution);         break;
        }
        if(improved){
            NL = {1, 2, 3, 4, 5, 6, 7};
        }else{
            std::swap(NL[n], NL.back());
            NL.pop_back();
        }
    }
    return solution;
}
