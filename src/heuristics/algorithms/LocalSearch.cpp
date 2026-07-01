#include "LocalSearch.hpp"
#include <algorithm>
#include <iomanip>
#include <random>
#include <iostream>

#include "../utils/objective.hpp"

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
    int best_i = -1;
    int best_j = -1;

    std::vector<Job> sequence = solution.sequence;

    for(size_t i = 1; i < sequence.size() - 1; i++){
        for(size_t j = i + 2; j < sequence.size() - 1; j++){
            std::vector<Job> temp = sequence;
            std::reverse(temp.begin() + i + 1, temp.begin() + j + 1);

            Solution tempSolution;
            tempSolution.sequence = temp;
            double delta = evaluate(tempSolution, problemData);
            if(delta < bestDelta){
                bestDelta = delta;
                best_i = i;
                best_j = j;
            }
        }
    }

    if(best_i != -1){
        std::reverse(solution.sequence.begin() + best_i + 1, solution.sequence.begin() + best_j + 1);
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

    int best_i = -1;
    int best_j = -1;

    const std::vector<Job>& sequence = solution.sequence;
    int n = (int)sequence.size();

    // i: primeira posição do segmento; i+k-1 deve ser <= n-2 (antes do dummy final)
    for(int i = 1; i <= n - 1 - k; i++){
        std::vector<Job> segment(sequence.begin() + i, sequence.begin() + i + k);

        // Após remover k elementos, o vetor tem n-k posições (índices 0..n-k-1).
        // Posições válidas para inserção: 1 .. n-k-1 (não move para cima do dummy final).
        // j==i significa reinserção na mesma posição → no-op, pulado.
        for(int j = 1; j <= n - k - 1; j++){
            if(j == i) continue;

            std::vector<Job> temp = sequence;
            temp.erase(temp.begin() + i, temp.begin() + i + k);
            temp.insert(temp.begin() + j, segment.begin(), segment.end());

            Solution tempSolution;
            tempSolution.sequence = temp;
            double delta = evaluate(tempSolution, problemData);
            if(delta < bestDelta){
                bestDelta = delta;
                best_i = i;
                best_j = j;
            }
        }
    }

    if(best_i != -1){
        // Aplica o melhor movimento encontrado na solução corrente
        std::vector<Job> segment(solution.sequence.begin() + best_i, solution.sequence.begin() + best_i + k);
        solution.sequence.erase(solution.sequence.begin() + best_i, solution.sequence.begin() + best_i + k);
        solution.sequence.insert(solution.sequence.begin() + best_j, segment.begin(), segment.end());
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
// O swap é feito in-place sobre a cópia `sequence` e desfeito após avaliar,
// evitando realocar um vetor temporário a cada iteração.
bool LocalSearch::bestImprovementSwap(const ProblemData &problemData, Solution &solution){
    double bestDelta = solution.objective_function;

    int best_i = -1;
    int best_j = -1;

    std::vector<Job> sequence = solution.sequence;

    for(size_t i = 1; i < solution.sequence.size() - 1; i++){
        for(size_t j = i + 1; j < solution.sequence.size() - 1; j++){
            std::swap(sequence[i], sequence[j]); // realiza o swap

            Solution temp;
            temp.sequence = sequence;
            double delta = evaluate(temp, problemData);
            if(delta < bestDelta){
                bestDelta = delta;
                best_i = i;
                best_j = j;
            }
            std::swap(sequence[i], sequence[j]); // desfaz o swap
        }
    }

    if (best_i != -1){
        std::swap(solution.sequence[best_i], solution.sequence[best_j]);
        solution.objective_function = bestDelta;
        return true;
    }
    return false;
}

// ---------------------------------------------------------------------------
// VNS — Variable Neighborhood Search
// ---------------------------------------------------------------------------
//
// Explora 5 vizinhanças em ordem aleatória:
//   1 = Swap      2 = OrOpt-1      3 = 2-Opt      4 = OrOpt-2      5 = OrOpt-3
//
// Regra de atualização:
//   - Se a vizinhança sortedada melhorou a solução → reseta NL (volta a explorar todas)
//   - Se não melhorou → remove essa vizinhança de NL (O(1) via swap+pop_back)
// Termina quando NL fica vazia: óptimo local em todas as vizinhanças simultaneamente.
void LocalSearch::algorithm(const ProblemData &problemData, Solution &solution){
    std::vector<int> NL = {1, 2, 3, 4, 5};
    bool improved = false;

    while(!NL.empty()){
        int n = std::rand() % NL.size();
        switch(NL[n]){
            case 1:
            improved = bestImprovementSwap(problemData, solution);
            break;
            case 2:
            improved = bestImprovementOrOpt(problemData, solution, 1);
            break;
            case 3:
            improved = bestImprovement2Opt(problemData, solution);
            break;
            case 4:
            improved = bestImprovementOrOpt(problemData, solution, 2);
            break;
            case 5:
            improved = bestImprovementOrOpt(problemData, solution, 3);
            break;
        }
        if(improved){
            std::string labels[] = {"", "Swap", "OrOpt1", "2Opt", "OrOpt2", "OrOpt3"};
            std::cout << "[improved] " << labels[NL[n]] << " → FO=" << solution.objective_function << std::endl;
            NL = {1, 2, 3, 4, 5};
        }else{
            // Remove vizinhança sem melhora em O(1)
            std::swap(NL[n], NL.back());
            NL.pop_back();
        }
    }
    std::cout << "Solução após busca local : " << std::endl;
    std::cout << "Sequence: ";
    for (const auto& job : solution.sequence) {
        std::cout << "[id=" << job.id << " release=" << job.release_date_slot << " due date=" << job.due_date_slot << "]";
    }
    std::cout << std::endl;
    std::cout << "Função objetivo: " << std::setprecision(15) << solution.objective_function << std::endl;
}
