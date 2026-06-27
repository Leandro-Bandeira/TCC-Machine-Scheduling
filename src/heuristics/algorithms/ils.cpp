#include "ils.hpp"
#include "../models/job.hpp"
#include "../utils/objective.hpp"
#include "LocalSearch.hpp"
#include <map>
#include <algorithm>
#include <iostream>
#include <random>

void ILS::construction(){
    Solution& solution = this->solution;
    const std::vector<Job>& jobs = this->problem_data.getJobs();
    const std::vector<std::vector<int>>& setup_matrix = this->problem_data.getSetupMatrix();
    std::map<int, std::vector<Job>> jobs_group_by_release;
    for(const auto& job : jobs) {
        if(job.idx == 0) continue;
        jobs_group_by_release[job.release_date_slot].push_back(job);
    }

    int r = 0;
    int insercaoIndice = 1;
    for(auto& [release_date, jobs] : jobs_group_by_release){
        std::vector<Job> CL;
        for(const auto& job: jobs){
            CL.push_back(job);
        }

        while(!CL.empty()){
            std::sort(CL.begin(), CL.end(), [=](const Job& a, const Job& b){
               return setup_matrix[a.idx][r] < setup_matrix[b.idx][r];
            });

            std::random_device rd;
            std::mt19937 gen(rd());
            std::uniform_int_distribution<> alpha(1, CL.size());

            std::vector<Job> RCL;
            int quantiaMelhoresCandidatos = alpha(gen);
            for(int i = 0; i < quantiaMelhoresCandidatos; i++){
                RCL.push_back(CL[i]);
            }

            unsigned seed(time(0));
            std::srand(seed);
            int posSelecionado = std::rand() % RCL.size();
            solution.sequence.insert(solution.sequence.begin() + insercaoIndice, RCL[posSelecionado]);

            r = RCL[posSelecionado].idx;
            insercaoIndice++;
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
