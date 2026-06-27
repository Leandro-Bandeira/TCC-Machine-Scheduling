#include "LocalSearch.hpp"
#include <algorithm>
#include <random>
#include <iostream>

#include "../utils/objective.hpp"

/*
 * O algoritmo 2Opt, vamos escolher 2 vértices não adjacentes e reinserir eles na rota, com a rota entre eles invertida
 * Por exemplo: Para i = 2 e j = 5, o movimento inclui a posição j e exclui a posição i
 * Temos o seguinte exemplo:
 * 0 1 (2) 3 4 (5) 6 7 8 9 0
 * 0 1 2 5 4 3 6 7 8 9
 * Tanto o 2opt como o swap sao simetricos, por isso so vamos o movimento par aum lado
 */
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
/*
 * O algoritmo OrOpt ou reinsertion, devemos pegar um elemento e mudar sua posição
 * dessa forma: 1 2 3 4 5 6 1, se temos i = 1 e j = 5, logo
 * 1 3 4 5 6 2 1
 * Seguimos o mesmo calculo de que o swap, diferente do swap, o reinsertion pode ser pra frente ou para trás
 */
bool LocalSearch::bestImprovementOrOpt(const ProblemData &problemData, Solution &solution){
    double bestDelta = solution.objective_function;

    int best_i = -1;
    int best_j = -1;

    std::vector<Job>sequence = solution.sequence;

    for(size_t i = 1; i < solution.sequence.size() - 1; i++){
        Job vi = solution.sequence[i];
        for(size_t j = 1; j < solution.sequence.size() - 1; j++){
            if (i == j) continue;

            std::vector<Job> temp = sequence;
            Job job = temp[i];
            temp.erase(temp.begin() + i);
            temp.insert(temp.begin() + j, job);

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

    if (best_i != -1){
        Job job = solution.sequence[best_i];
        solution.sequence.erase(solution.sequence.begin() + best_i);
        solution.sequence.insert(solution.sequence.begin() + best_j, job);
        solution.objective_function = bestDelta;
        return true;
    }
    return false;

}
/*
 * O algoritmo abaixo realiza o movimento de swap, suponha que temos uma solução do tipo
 * 1 2 3 4 5 1 e estamos aplicando o swap entre i = 1 e j = 4
 * Logo teremos a nova rota dada por: 1 5 3 4 2 1
 * Por enquanto nossa avaliação será dada pelo delta = custoNovo - custoAntigo, delta < 0, improvement
 * O swap considera sempre as posições i e i + 1, justamente porque a troca é equivalente, não adianta estar na posição  i + 2 e olhar para trás
 */
bool LocalSearch::bestImprovementSwap(const ProblemData &problemData, Solution &solution){
    double bestDelta = solution.objective_function;

    int best_i = -1;
    int best_j = -1;

    std::vector<Job>sequence = solution.sequence;

    for(size_t i = 1; i < solution.sequence.size() - 1; i++){
        Job vi = solution.sequence[i];
        for(size_t j = i + 1; j < solution.sequence.size() - 1; j++){
            std::swap(sequence[i], sequence[j]); // Realiza o Swap

            Solution temp;
            temp.sequence = sequence;
            double delta = evaluate(temp, problemData);
            if(delta < bestDelta){
                bestDelta = delta;
                best_i = i;
                best_j = j;
            }
            std::swap(sequence[i], sequence[j]); // Desfaz o swap
        }
    }

    if (best_i != -1){
        std::swap(solution.sequence[best_i], solution.sequence[best_j]);
        solution.objective_function = bestDelta;
        return true;
    }
    return false;

}


void LocalSearch::algorithm(const ProblemData &problemData, Solution &solution){
    std::vector<int> NL = {1, 2, 3};
    bool improved = false;

    while(!NL.empty()){
        int n = std::rand() % NL.size();
        switch(NL[n]){
            case 1:
            improved = bestImprovementSwap(problemData, solution);
            break;
            case 2:
            improved = bestImprovementOrOpt(problemData, solution);
            break;
            case 3:
            improved = bestImprovement2Opt(problemData, solution);
            break;
        }
        if(improved){
            std::string movement = (NL[n] == 1) ? "Swap" : (NL[n] == 2) ? "OrOpt" : "2Opt";
            std::cout << "[improved] " << movement << " → FO=" << solution.objective_function << std::endl;
            NL = {1, 2, 3};
        }else{
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
    std::cout << "Função objetivo: " << solution.objective_function << std::endl;

}
