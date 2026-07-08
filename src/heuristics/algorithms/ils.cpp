#include "ils.hpp"
#include "../models/job.hpp"
#include "../utils/objective.hpp"
#include "../utils/utils.hpp"
#include "LocalSearch.hpp"
#include <cmath>
#include <iomanip>
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
Solution ILS::construction(){
    Solution solution;
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
    return solution;
}

/*
 * Perturbação do ILS: escolhe o operador conforme a topologia da instância.
 *
 *   - 1 máquina  -> (l, l')-block swap intra-máquina (não há outra rota pra
 *                    trocar jobs, então a diversificação tem que vir de
 *                    dentro da própria rota).
 *   - >1 máquinas -> Multiple (1,1)-insertion inter-máquina (troca jobs
 *                    entre rotas, repetida 1 a 3 vezes).
 */
Solution ILS::perturbation(Solution solution){

    int count_routes = (int)solution.routes.size();

    if(count_routes == 1){
        /*
         * (l, l')-block swap intra-machine.
         * Sorteia dois blocos de jobs A (tamanho l) e B (tamanho l'), com
         * l, l' ∈ [2, N/4] (N = qtd de jobs reais na rota), e troca as
         * posições dos dois blocos dentro da mesma rota.
         */
        int lower = 2;
        std::vector<Job>& current_route = solution.routes[0];

        // N = jobs reais, sem contar os dois dummies (início e fim da rota)
        int N = (int)current_route.size() - 2;
        int upper = N / 4;

        // rota curta demais pra caber dois blocos de tamanho >= 2 cada
        if (upper >= 2) {
            int l  = lower + std::rand() % (upper - lower + 1); // tamanho do bloco A, [2, N/4]
            int lp = lower + std::rand() % (upper - lower + 1); // tamanho do bloco B, [2, N/4]

            // índices reais válidos: 1..N (0 e size-1 são os dummies)
            int i = 1 + std::rand() % (N - l + 1);  // início do bloco A
            int j_min = i + l;                      // B só pode começar depois do fim de A (sem overlap)
            int j_max = N - lp + 1;                 // B precisa caber até o fim da rota

            // não há espaço pra encaixar B depois de A com esse (l, l') sorteado
            if (j_min <= j_max) {
                int j = j_min + std::rand() % (j_max - j_min + 1); // início do bloco B

                // reconstrói a rota trocando A <-> B (blocos de tamanhos possivelmente diferentes)
                std::vector<Job> new_route;
                new_route.reserve(current_route.size());

                for (int k = 0;       k < i; k++) new_route.push_back(current_route[k]); // trecho antes de A, inalterado
                for (int k = j;       k < j + lp; k++) new_route.push_back(current_route[k]); // bloco B ocupa o lugar de A
                for (int k = i + l;   k < j; k++) new_route.push_back(current_route[k]); // trecho entre A e B, inalterado
                for (int k = i;       k < i + l; k++) new_route.push_back(current_route[k]); // bloco A ocupa o lugar de B
                for (int k = j + lp;  k < (int)current_route.size(); k++) new_route.push_back(current_route[k]); // trecho depois de B, inalterado

                current_route = new_route;
            }
        }
    }
    else{
        /*
         * Multiple (1,1)-insertion inter-machine.
         * A cada repetição: sorteia duas rotas k != k' e um job em cada uma;
         * remove os dois jobs de suas rotas e reinsere cada um na rota
         * oposta, em uma posição sorteada de forma independente.
         * Repete de 1 a 3 vezes consecutivas.
         */
        int max_repeat_perturbation = 3;
        int repeat_perturbation = (std::rand() % max_repeat_perturbation) + 1;

        int count_repeat = 0;
        while(count_repeat < repeat_perturbation){

            // Sorteia duas rotas diferentes (kp != k) por rejeição
            int k = std::rand() % count_routes;
            int kp;
            do{
                kp = std::rand() % count_routes;
            }while(kp == k);
            std::vector<Job>& route_k = solution.routes[k];
            std::vector<Job>& route_kp = solution.routes[kp];

            // Rota só com dummies, sem job real pra trocar: pula essa repetição
            if((int)route_k.size() <= 2 || (int)route_kp.size() <= 2){
                count_repeat++;
                continue;
            }

            // Sorteia um job (índice) real em cada rota, excluindo os dummies
            int j = 1 + std::rand() % ((int)route_k.size() - 2);
            int jp = 1 + std::rand() % ((int)route_kp.size() - 2);

            Job job_k = route_k[j];
            Job job_kp = route_kp[jp];

            // Remove os dois jobs de suas rotas de origem
            route_k.erase(route_k.begin() + j);
            route_kp.erase(route_kp.begin() + jp);

            // Sorteia a posição de destino de cada job na rota oposta,
            // já considerando o tamanho da rota após a remoção
            int pos_k  = 1 + std::rand() % ((int)route_k.size() - 1);  // onde job_kp entra em k
            int pos_kp = 1 + std::rand() % ((int)route_kp.size() - 1); // onde job_k entra em k'

            route_k.insert(route_k.begin() + pos_k, job_kp);
            route_kp.insert(route_kp.begin() + pos_kp, job_k);

            count_repeat++;
        }
    }
    solution.objective_function = evaluate(solution, problem_data);

    std::cout << "Função objetivo após a perturbação: " << std::setprecision(15) << solution.objective_function << std::endl;
    return solution;
}

/*
 * ILS (Iterated Local Search) com multi-start via GRASP.
 *
 * Para cada iteração externa (m_maxIter):
 *   1. construction()        — constrói solução inicial aleatória (GRASP)
 *   2. LocalSearch()         — desce até ótimo local; resultado vira `best`
 *   3. Loop ILS (m_maxIterILS):
 *      a. perturbation(best) — escapa do ótimo local via block-swap intra-máquina
 *      b. LocalSearch()      — desce até novo ótimo local
 *      c. se melhorou `best`: atualiza e reseta contador (aceita apenas melhora)
 *   4. se `best` < `bestAllSolution`: atualiza o melhor global
 *
 * Critério de aceitação: best-improvement puro (sem aceitar piora).
 */
void ILS::algorithm(){

    std::srand(time(0));

    Solution bestAllSolution;
    for(int i = 0; i < this->m_maxIter; i++){
        Solution s = construction();

        Solution best = s;

        int iterILS = 0;
        while(iterILS <= this->m_maxIterILS){
            s = LocalSearch::algorithm(problem_data, s);

            if(s.objective_function < best.objective_function){
                best = s;
                iterILS = 0;
            }
            s = perturbation(best);
            iterILS++;
        }

        if(best.objective_function < bestAllSolution.objective_function){
            bestAllSolution = best;
        }
    }

    printRoutes(bestAllSolution);
    this->solution = bestAllSolution;
}
