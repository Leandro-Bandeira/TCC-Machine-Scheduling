#include "ils.hpp"
#include "../models/job.hpp"

#include <map>
#include <algorithm>
#include <iostream>
#include <random>


/* Estamos retornando um ponteiro unico, ponteiro unico não precisamos nos preocupar em deletar sua regiao de memoria
 * ao sair do escopo, ele é deltado sozinho. Porém perceba, que ele é criado dentro do escopo de construction
 * mas ao ser retornado, é movido para outro escopo
  */
std::unique_ptr<Solution> ILS::contruction(){
    std::unique_ptr<Solution> solution = std::make_unique<Solution>();
    const std::vector<Job>& jobs = this->problem_data.getJobs();
    const std::vector<std::vector<int>>& setup_matrix = this->problem_data.getSetupMatrix();
    // Precisamos agrupar os dados por release date, e que os release dates estejam agrupados de forma crescente
    // O map ja ordena de forma automática, todas as operacoes do map são em O(logn)
    std::map<int, std::vector<Job>> jobs_group_by_release;
    for(const auto& job : jobs) {
        if(job.idx == 0) continue;
        jobs_group_by_release[job.release_date_slot].push_back(job);
    }


    /* Vamos percorrer todos os grupos e em cada grupo aplicar a heuristica de inserção mais barata */
    int r = 0; // Job dummy (Origem)
    int insercaoIndice = 1;
    for(auto& [release_date, jobs] : jobs_group_by_release){
        std::vector<Job> CL; // Jobs candidatos

        for(const auto& job: jobs){
            CL.push_back(job);
        }

        while(!CL.empty()){

            /* O método sort pode receber uma função como terceiro parametro, dito isso, ele está recebendo uma função
               lambda, cada valor do vetor CL, será passado para a função em forma de a e b, por passagem de referencia
               dessa forma, estamos comparado todos em relacao a sua distancia ao nó r */
            std::sort(CL.begin(), CL.end(), [=](const Job& a, const Job& b){
               return setup_matrix[a.idx][r] < setup_matrix[b.idx][r];
            });

            /* Gera valor aleatório entre 1 e o tamanho de CL */
            std::random_device rd;
            std::mt19937 gen(rd());
            std::uniform_int_distribution<>alpha(1, CL.size());

            /* Vamos pegar todos os melhores candidados dado de acordo com o valor aleatorio */
            std::vector <Job> RCL;
            int quantiaMelhoresCandidatos = alpha(gen);
            for(int i = 0; i < quantiaMelhoresCandidatos; i++){
                RCL.push_back(CL[i]);
            }

            /* Seleciona uma posicao aleatoria de RCL */
            unsigned seed(time(0));
            std::srand(seed);

            int posSelecionado = std::rand() % RCL.size();
            solution->sequence.insert(solution->sequence.begin() + insercaoIndice, RCL[posSelecionado]);

            r = RCL[posSelecionado].idx;
            insercaoIndice++;
            // posSelecionado é o mesmo de RCL, já que são os mesmos vetores, porém de tamanhos diferentes
            // Dessa forma com o swap, conseguimos deletar em O(1)
            std::swap(CL[posSelecionado], CL.back());
            CL.pop_back();
        }
    }
    std::cout << "Sequence: ";
    for (const auto& job : solution->sequence) {
        std::cout << "[id=" << job.id << " release=" << job.release_date_slot << "] ";
    }
    std::cout << std::endl;

    return solution;
};
