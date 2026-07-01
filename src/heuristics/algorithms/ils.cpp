#include "ils.hpp"
#include "../models/job.hpp"
#include "../utils/objective.hpp"
#include "LocalSearch.hpp"
#include <map>
#include <algorithm>
#include <iostream>
#include <random>

// Fase de construção GRASP (Greedy Randomized Adaptive Search Procedure).
//
// Estratégia:
//   - Jobs são agrupados por release_date para respeitar a data de liberação.
//   - Dentro de cada grupo, ordena-se por setup crescente em relação ao último job
//     inserido (critério guloso adaptativo).
//   - Uma quantidade aleatória `alpha` dos melhores candidatos forma a RCL
//     (Restricted Candidate List). Um elemento é escolhido aleatoriamente da RCL.
//   - O job escolhido é removido da lista de candidatos (O(1) via swap+pop_back).
//
// Isso introduz diversificação: ao variar o tamanho da RCL entre 1 e |CL|,
// a construção oscila entre totalmente gulosa (alpha=1) e aleatória (alpha=|CL|).
void ILS::construction(){
    Solution& solution = this->solution;
    const std::vector<Job>& jobs = this->problem_data.getJobs();
    const std::vector<std::vector<int>>& setup_matrix = this->problem_data.getSetupMatrix();

    // Agrupa jobs por release_date — map ordena automaticamente por chave crescente
    std::map<int, std::vector<Job>> jobs_group_by_release;
    for(const auto& job : jobs) {
        if(job.idx == 0) continue; // pula o dummy
        jobs_group_by_release[job.release_date_slot].push_back(job);
    }

    int r = 0;           // idx do último job inserido (0 = dummy → sem setup inicial)
    int insercaoIndice = 1; // posição de inserção na sequência (antes do dummy final)

    for(auto& [release_date, jobs] : jobs_group_by_release){
        std::vector<Job> CL(jobs); // lista de candidatos do grupo

        while(!CL.empty()){
            // Ordena candidatos pelo setup em relação ao último job inserido
            std::sort(CL.begin(), CL.end(), [=](const Job& a, const Job& b){
               return setup_matrix[a.idx][r] < setup_matrix[b.idx][r];
            });

            // alpha: tamanho aleatório da RCL ∈ [1, |CL|]
            std::random_device rd;
            std::mt19937 gen(rd());
            std::uniform_int_distribution<> alpha(1, CL.size());

            std::vector<Job> RCL;
            int quantiaMelhoresCandidatos = alpha(gen);
            for(int i = 0; i < quantiaMelhoresCandidatos; i++){
                RCL.push_back(CL[i]);
            }

            // Seleciona aleatoriamente um job da RCL e insere na sequência
            unsigned seed(time(0));
            std::srand(seed);
            int posSelecionado = std::rand() % RCL.size();
            solution.sequence.insert(solution.sequence.begin() + insercaoIndice, RCL[posSelecionado]);

            r = RCL[posSelecionado].idx;
            insercaoIndice++;

            // Remove o job selecionado de CL em O(1): troca com o último e remove o último
            std::swap(CL[posSelecionado], CL.back());
            CL.pop_back();
        }
    }

    std::cout << "Solução na construção: " << std::endl;
    std::cout << "Sequence: ";
    for (const auto& job : solution.sequence) {
        std::cout << "[id=" << job.id << " release=" << job.release_date_slot << " due date=" << job.due_date_slot << "]";
    }
    std::cout << std::endl;

    solution.objective_function = evaluate(solution, this->problem_data);
    std::cout << "Função objetivo: " << solution.objective_function << std::endl;
}

void ILS::algorithm(){
    this->construction();
    LocalSearch::algorithm(this->problem_data, this->solution);
}
