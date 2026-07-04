#include "ils.hpp"
#include "../models/job.hpp"
#include "../utils/objective.hpp"
#include "../utils/utils.hpp"
#include "LocalSearch.hpp"
#include <map>
#include <algorithm>
#include <iostream>
#include <random>

// Fase de construção GRASP (Greedy Randomized Adaptive Search Procedure).
//
// Estratégia:
//   - Jobs são agrupados por release_date para respeitar a data de liberação.
//   - Para cada job: sorteia uma rota aleatória m entre as count_machines rotas disponíveis.
//   - Ordena candidatos por setup crescente em relação ao último job inserido na rota m.
//   - Uma quantidade aleatória `alpha` dos melhores candidatos forma a RCL
//     (Restricted Candidate List). Um elemento é escolhido aleatoriamente da RCL.
//   - O job escolhido é inserido na rota m e removido de CL em O(1) via swap+pop_back.
//
// Isso introduz diversificação: ao variar o tamanho da RCL entre 1 e |CL|,
// a construção oscila entre totalmente gulosa (alpha=1) e aleatória (alpha=|CL|).
void ILS::construction(){
    Solution& solution = this->solution;
    const std::vector<Job>& jobs = this->problem_data.getJobs();
    const std::vector<std::vector<int>>& setup_matrix = this->problem_data.getSetupMatrix();
    const int count_machines = this->problem_data.getCountMachines();

    // Inicializa count_machines rotas, cada uma com [dummy, dummy]
    solution.routes.resize(count_machines, {Job(0,0,0,0,0,0), Job(0, 0, 0, 0, 0, 0)});
    // Agrupa jobs por release_date — map ordena automaticamente por chave crescente
    std::map<int, std::vector<Job>> jobs_group_by_release;
    for(const auto& job : jobs) {
        if(job.idx == 0) continue; // pula o dummy
        jobs_group_by_release[job.release_date_slot].push_back(job);
    }

    std::vector<int> r(count_machines, 0); // idx do último job inserido (0=dummy, sem setup inicial), temos um valor de r para cada rota
    std::vector<int>insercaoIndice(count_machines, 1); // posição de inserção na sequência (antes do dummy final)

    std::mt19937 gen(std::random_device{}());

    for(auto& [release_date, jobs] : jobs_group_by_release){
        std::vector<Job> CL(jobs); // lista de candidatos do grupo

        while(!CL.empty()){
            // Sorteia rota aleatoria
            int m = std::rand() % count_machines;

            // Ordena candidatos pelo setup em relação ao último job inserido, dentro daquela rota
            std::sort(CL.begin(), CL.end(), [&](const Job& a, const Job& b){
                return setup_matrix[r[m]][a.idx] < setup_matrix[r[m]][b.idx];
            });

            // alpha: tamanho aleatório da RCL ∈ [1, |CL|]
            std::uniform_int_distribution<> alpha(1, (int)CL.size());
            int quantiaMelhoresCandidatos = alpha(gen);

            std::vector<Job> RCL(CL.begin(), CL.begin() + quantiaMelhoresCandidatos);

            // Seleciona aleatoriamente um job da RCL e insere na sequência
            int posSelecionado = std::rand() % RCL.size();

            solution.routes[m].insert(
                solution.routes[m].begin() + insercaoIndice[m], RCL[posSelecionado]
            );
            r[m] = RCL[posSelecionado].idx;
            insercaoIndice[m]++;

            // Remove o job selecionado de CL em O(1): troca com o último e remove o último
            std::swap(CL[posSelecionado], CL.back());
            CL.pop_back();
        }
    }

    solution.objective_function = evaluate(solution, this->problem_data);
    printRoutes(solution);
}

void ILS::algorithm(){
    std::srand(time(0));
    this->construction();
    LocalSearch::algorithm(this->problem_data, this->solution);
}
