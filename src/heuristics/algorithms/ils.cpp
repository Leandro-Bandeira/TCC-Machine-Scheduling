#include "ils.hpp"
#include "../models/job.hpp"
#include "../utils/objective.hpp"
#include "../utils/read_instance.hpp"
#include "../utils/utils.hpp"
#include "../utils/Debug.hpp"
#include "../utils/params.hpp"
#include "LocalSearch.hpp"
#include <cmath>
#include <iomanip>
#include <map>
#include <algorithm>
#include <iostream>
#include <random>
#include <chrono>


// Fase de construção GRASP (Greedy Randomized Adaptive Search Procedure) - Estratégia ERD-GRASP Global.
//
// Estratégia (A):
//   - Todos os jobs reais são reunidos na lista de candidatos CL e ordenados por release_date_slot crescente
//     (desempate por due_date_slot).
//   - A cada passo, define-se a RCL (Restricted Candidate List) com base nos k candidatos com menores release dates.
//   - Um elemento é sorteado aleatoriamente da RCL.
//   - O job escolhido é alocado na máquina paralela com menor tempo de término acumulado (Earliest Available Machine).
//   - O job é inserido no final da rota (antes do dummy final) e removido de CL.
Solution ILS::construction(){
    Solution solution;
    const std::vector<Job>& jobs = this->problem_data.getJobs();
    const int count_machines = this->problem_data.getCountMachines();

    // Inicializa count_machines rotas reais + 1 rota para o pool virtual de não-alocados
    solution.routes.resize(count_machines + 1);
    solution.initEvalBuffers(this->problem_data.getNumResources(), this->problem_data.getNumWords(), count_machines);

    // Lista de candidatos global (todos os jobs reais, excluindo o dummy)
    std::vector<Job> CL;
    CL.reserve(jobs.size());
    for(const auto& job : jobs) {
        if(job.idx == 0) continue; // pula o dummy
        CL.push_back(job);
    }

    // Ordena CL por release_date_slot crescente, desempate por due_date_slot
    std::sort(CL.begin(), CL.end(), [](const Job& a, const Job& b){
        if(a.release_date_slot != b.release_date_slot)
            return a.release_date_slot < b.release_date_slot;
        return a.due_date_slot < b.due_date_slot;
    });

    std::mt19937 gen(std::random_device{}());
    std::uniform_real_distribution<double> dist_alpha(0.0, 1.0);

    while(!CL.empty()){
        // Parâmetro alpha: sorteia valor aleatório em [0, 1]
        double alpha = dist_alpha(gen);
        int k = std::max(1, (int)std::ceil(alpha * CL.size()));

        // Sorteia aleatoriamente um job entre os k melhores (menores release dates)
        int posSelecionado = std::rand() % k;
        Job selected_job = CL[posSelecionado];

        // Sorteia aleatoriamente uma máquina paralela
        int m = std::rand() % count_machines;

        // Insere o job na rota escolhida
        solution.routes[m].push_back(selected_job);

        // Remove o job selecionado de CL
        CL.erase(CL.begin() + posSelecionado);
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
         * l, l' ∈ [2, N/4] (N = qtd de jobs na rota), e troca as
         * posições dos dois blocos dentro da mesma rota.
         */
        int lower = 2;
        std::vector<Job>& current_route = solution.routes[0];
        int N = (int)current_route.size();
        int upper = N / 4;

        if (upper >= 2) {
            int l  = lower + std::rand() % (upper - lower + 1); // tamanho do bloco A, [2, N/4]
            int lp = lower + std::rand() % (upper - lower + 1); // tamanho do bloco B, [2, N/4]

            // K = posições livres para as três lacunas; sempre >= 0 pois l+lp <= N/2
            int K = N - l - lp;

            // Sorteia dois pontos em [0, K] e os ordena (Stars and Bars)
            int r1 = std::rand() % (K + 1);
            int r2 = std::rand() % (K + 1);
            int a  = std::min(r1, r2); // gap_s = a  →  i = a
            int b  = std::max(r1, r2); // gap_m = b - a , gap_e = K - b

            int i = a;       // início do bloco A: [0, N-l-lp]
            int j = b + l;   // início do bloco B: sempre >= i + l, sempre cabe na rota

            // reconstrói a rota trocando A <-> B (blocos de tamanhos possivelmente diferentes)
            std::vector<Job> new_route;
            new_route.reserve(current_route.size());

            for (int k = 0;       k < i;                      k++) new_route.push_back(current_route[k]); // trecho antes de A, inalterado
            for (int k = j;       k < j + lp;                 k++) new_route.push_back(current_route[k]); // bloco B ocupa o lugar de A
            for (int k = i + l;   k < j;                      k++) new_route.push_back(current_route[k]); // trecho entre A e B, inalterado
            for (int k = i;       k < i + l;                  k++) new_route.push_back(current_route[k]); // bloco A ocupa o lugar de B
            for (int k = j + lp;  k < N;                      k++) new_route.push_back(current_route[k]); // trecho depois de B, inalterado

            current_route = new_route;
            solution.invalidateRoute(0);
        }
        else if (N >= 2){
            int pos1 = std::rand() % N;
            int pos2 = std::rand() % (N - 1);
            if (pos2 >= pos1) pos2++;
            std::swap(current_route[pos1], current_route[pos2]);
            solution.invalidateRoute(0);
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

            // Rota vazia, sem job real pra trocar: pula essa repetição
            if(route_k.empty() || route_kp.empty()){
                count_repeat++;
                continue;
            }

            // Sorteia um job (índice) em cada rota
            int j = std::rand() % route_k.size();
            int jp = std::rand() % route_kp.size();

            Job job_k = route_k[j];
            Job job_kp = route_kp[jp];

            // Remove os dois jobs de suas rotas de origem
            route_k.erase(route_k.begin() + j);
            route_kp.erase(route_kp.begin() + jp);

            // Sorteia a posição de destino de cada job na rota oposta,
            // de 0 até o tamanho da rota pós-remoção (inclusive)
            int pos_k  = std::rand() % (route_k.size() + 1);  // onde job_kp entra em k
            int pos_kp = std::rand() % (route_kp.size() + 1); // onde job_k entra em k'

            route_k.insert(route_k.begin() + pos_k, job_kp);
            route_kp.insert(route_kp.begin() + pos_kp, job_k);
            solution.invalidateRoute(k);
            solution.invalidateRoute(kp);

            count_repeat++;
        }
    }
    solution.objective_function = evaluate(solution, problem_data);

    //std::cout << "Função objetivo após a perturbação: " << std::setprecision(15) << solution.objective_function << std::endl;
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
void ILS::algorithm(const std::string& input_path, int machine_id){
    this->problem_data.logInstanceData(input_path, this->m_maxIter, this->m_maxIterILS);
    auto t0 = std::chrono::steady_clock::now();


    unsigned int seed = time(0);
    //seed = 1785203589;
    std::srand(seed);
    //std::cout << "Seed: " << seed << std::endl;

    Solution bestAllSolution;
    
    for(int i = 0; i < this->m_maxIter; i++){
        Debug::log("Iteração: "  + std::to_string(i));
        Solution s = construction();

        Solution best = s;

        int iterILS = 0;
        while(iterILS <= this->m_maxIterILS){
            Debug::log("IterIls " + std::to_string(iterILS));   
            s = LocalSearch::algorithm(problem_data, s);

            if(best.objective_function - s.objective_function > EPS_FO){
                best = s;
                Debug::log("Resetou iterIls");
                iterILS = 0;
            }
            s = perturbation(best);
            iterILS++;
        }

        if(bestAllSolution.objective_function - best.objective_function > EPS_FO ){
            bestAllSolution = best;
        }
    }

    auto t1 = std::chrono::steady_clock::now();
    double elapsed = std::chrono::duration<double>(t1 - t0).count();
    std::cout << "Tempo total: " << elapsed << "s" << std::endl;

    // LocalSearch só atualiza objective_function após cada movimento, sem re-executar
    // evaluate() na solução real (roda apenas em cópias temporárias). Por isso job.start/end
    // ficam desatualizados em relação à ordem final das rotas — resincroniza aqui antes de reportar.
    bestAllSolution.objective_function = evaluate(bestAllSolution, problem_data);
    printRoutes(bestAllSolution);
    this->solution = bestAllSolution;

    std::cout << "Best solution: " << bestAllSolution.objective_function << std::endl;

    if (!input_path.empty()) {
        ReadInstance::saveOutputJson(input_path, machine_id, bestAllSolution, elapsed);
    }
}
