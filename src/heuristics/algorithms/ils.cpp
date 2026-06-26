#include "ils.hpp"
#include "../models/job.hpp"

#include <map>
#include <algorithm>
#include <iostream>
#include <random>

/*
 * Para cada job, calculamos seu completion time
 * a partir do segundo, o completion_time é igual
 * ao tempo do término do anterior + seu release date + seu processing_time
 * Para cada job, conseguimos saber se ele passou do seu due date ou não, assim sabemos o somatorio do tardiness
 * E caso seu inicio seja maior que o ultimo slot, logo o job não foi alocado, dessa forma conseguimos calcular a função objetivo
 */
double ILS::evaluate(const Solution& solution){
   double cost = 0.0;
   std::vector<Job> sequence = solution.sequence;
   const std::vector<std::vector<int>>& setup_matrix = this->problem_data.getSetupMatrix();
   const int H = this->problem_data.getH();
   const int numJobs = this->problem_data.getNumJobs();

   // Somatorio do tardiness
   int sum_tardiness = 0;

   // Somatorio de jobs não alocados
   int sum_jobs_not_allocated = 0;
   double weight_not_allocated = numJobs * H + 1;

   // Somatório do completion time
   int sum_completion_time = 0;
   double epsilon = 1/weight_not_allocated;

   int last_completion_time = 0;
   int prev_idx = 0;
   for(size_t i = 0; i < sequence.size(); i++){
       Job job = sequence[i];
       if(job.idx == 0) continue;
       int current_indx = job.idx;
       int setup = 0;

       if (prev_idx){
           setup = setup_matrix[prev_idx][current_indx];
       }

       int start = std::max(last_completion_time + setup, job.release_date_slot);

       if (start > H){
           sum_jobs_not_allocated += 1;
           continue;
       }
       int current_completion_time = start + job.processing_slots;

       sum_tardiness += std::max(0, current_completion_time - job.due_date_slot);

       prev_idx = current_indx;
       sum_completion_time += current_completion_time;
       last_completion_time = current_completion_time;

   }

   return sum_tardiness + weight_not_allocated * sum_jobs_not_allocated + epsilon * sum_completion_time;
}

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
        std::cout << "[id=" << job.id << " release=" << job.release_date_slot  << " due date=" << job.due_date_slot << "]";
    }
    std::cout << std::endl;
    solution->objective_function = this->evaluate(*solution);
    std::cout << "Função objetivo: " << solution->objective_function << std::endl;
    return solution;
};
