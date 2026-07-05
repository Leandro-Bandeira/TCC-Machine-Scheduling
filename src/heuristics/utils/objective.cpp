#include "objective.hpp"
#include "../models/job.hpp"
#include <algorithm>
#include <unordered_map>

// Avalia todas as rotas da solução e retorna a FO total.
//
// Para cada rota, para cada job (ignorando dummies idx=0):
//   1. earliest = max(last_completion + setup, release_date, first_slot)
//   2. Snapa para o menor start_slot >= earliest
//   3. start > H → job não alocado (penalidade W)
//
// FO total = soma das FOs de cada rota individualmente.
//
// Após avaliar todas as rotas, verifica a restrição de big_setup cross-rota:
// jobs com mesmo resource_id em rotas diferentes devem ter gap >= big_setup.
//
// Exemplo com count_machines=2, big_setup=15:
//   rota[0]: job_A(resource=1, start=0, end=10)
//   rota[1]: job_C(resource=1, start=0, end=8)
//
//   scheduled agrupado por resource_id=1, ordenado por start:
//     jobs[0] = {start=0, end=8,  route=1}  ← job_C
//     jobs[1] = {start=0, end=10, route=0}  ← job_A
//
//   Par consecutivo: rotas diferentes → jobs[1].start=0 < jobs[0].end + big_setup = 8+15=23
//   → violação → total += W
//
// A verificação usa pares consecutivos após ordenar por start: suficiente pois
// se (i, i+1) não viola, qualquer par mais distante no tempo também não viola.
double evaluate(Solution& solution, const ProblemData& problem_data) {
    const std::vector<std::vector<int>>& setup_matrix = problem_data.getSetupMatrix();
    const int H = problem_data.getH();
    const int first_slot = problem_data.getFirstSlot();
    const int numJobs = problem_data.getNumJobs() - 1;
    const int big_setup = problem_data.getBigSetup();
    const int count_machines = problem_data.getCountMachines();

    const std::vector<int>& start_slots = problem_data.getStartSlots();
    const double weight_not_allocated = numJobs * H + 1;
    const double epsilon = 1.0 / weight_not_allocated;

    double total = 0.0;

    // Coleta jobs agendados para verificar big_setup cross-rota
    struct ScheduledJob {int resource_id, start, end, route;};
    std::vector<ScheduledJob> scheduled;

    for (int m = 0; m < (int)solution.routes.size(); m++) {
        auto& route = solution.routes[m];
        int sum_tardiness = 0;
        int sum_jobs_not_allocated = 0;
        int sum_completion_time = 0;
        int last_completion_time = 0;
        int prev_idx = 0;

        for (Job& job : route) {
            if (job.idx == 0) continue;

            int current_idx = job.idx;
            int setup = prev_idx ? setup_matrix[prev_idx][current_idx] : 0;

            int earliest = std::max({last_completion_time + setup, job.release_date_slot, first_slot});

            auto it = std::lower_bound(start_slots.begin(), start_slots.end(), earliest);
            int start = (it != start_slots.end()) ? *it : H + 1;

            if (start > H) {
                job.start = -1;
                job.end = -1;
                sum_jobs_not_allocated += 1;
                continue;
            }

            int current_completion_time = start + job.processing_slots;
            job.start = start;
            job.end = current_completion_time;
            sum_tardiness += std::max(0, current_completion_time - job.due_date_slot);
            prev_idx = current_idx;
            sum_completion_time += current_completion_time;
            last_completion_time = current_completion_time;

            scheduled.push_back({job.resource_id, start, current_completion_time, m});
        }

        total += sum_tardiness + weight_not_allocated * sum_jobs_not_allocated + epsilon * sum_completion_time;
    }

    // Só verifica big_setup se há mais de uma rota (restrição cross-rota)
    if(count_machines > 1){
        // Agrupa jobs agendados por resource_id
        std::unordered_map<int, std::vector<ScheduledJob>> by_resource;
        for (const auto& job : scheduled)
            by_resource[job.resource_id].push_back(job);

        for (auto& [resource_id, jobs] : by_resource) {
            if (jobs.size() < 2) continue; // resource exclusivo de uma rota: sem conflito possível

            // Ordena por start para verificar pares consecutivos
            std::sort(jobs.begin(), jobs.end(), [](const ScheduledJob& a, const ScheduledJob& b){
                return a.start < b.start;
            });

            for(int i = 0; i < (int)jobs.size() - 1; i++){
                // Restrição só se aplica a rotas diferentes
                if(jobs[i].route != jobs[i + 1].route){
                    // jobs[i+1] deve começar ao menos big_setup após jobs[i] terminar
                    if(jobs[i + 1].start < jobs[i].end + big_setup)
                        total += weight_not_allocated;
                }
            }
        }
    }
    return total;
}
