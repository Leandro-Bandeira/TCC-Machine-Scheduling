#include "objective.hpp"
#include "../models/job.hpp"
#include <algorithm>

// Simula o escalonamento da sequência e calcula a função objetivo.
//
// Para cada job (ignorando os dummies de idx=0), determina o slot de início real:
//   1. Calcula o tempo mínimo possível: max(termino_anterior + setup, release_date, first_slot)
//   2. Snapa para o menor start_slot disponível >= esse mínimo (via lower_bound)
//   3. Se não existe start_slot válido (start > H), o job não é alocado
//
// O setup entre jobs consecutivos usa setup_matrix[prev_idx][current_idx].
// Para o primeiro job real, prev_idx=0 → linha do dummy → setup = 0.
double evaluate(const Solution& solution, const ProblemData& problem_data) {
    std::vector<Job> sequence = solution.sequence;
    const std::vector<std::vector<int>>& setup_matrix = problem_data.getSetupMatrix();
    const int H = problem_data.getH();
    const int first_slot = problem_data.getFirstSlot();
    const int numJobs = problem_data.getNumJobs() - 1; // desconta o dummy
    const std::vector<int>& start_slots = problem_data.getStartSlots();
    int count_machines = problem_data.getCountMachines();
    int big_setup = problem_data.getBigSetup();

    int sum_tardiness = 0;
    int sum_jobs_not_allocated = 0;
    double weight_not_allocated = numJobs * H + 1; // W: grande o suficiente para dominar qualquer tardiness
    int sum_completion_time = 0;
    double epsilon = 1.0 / weight_not_allocated;   // desempate por completion time total

    int last_completion_time = 0;
    int prev_idx = 0;
    for (const Job& job : sequence) {
        if (job.idx == 0) continue; // pula os dummies de início/fim

        int current_idx = job.idx;
        int setup = prev_idx ? setup_matrix[prev_idx][current_idx] : 0;

        // Menor instante em que o job pode começar
        int earliest = std::max({last_completion_time + setup, job.release_date_slot, first_slot});

        // Snap para o próximo start_slot disponível (máquina não pode iniciar em qualquer momento)
        auto it = std::lower_bound(start_slots.begin(), start_slots.end(), earliest);
        int start = (it != start_slots.end()) ? *it : H + 1;

        if (start > H) {
            // Não há slot disponível dentro do horizonte — job não alocado
            sum_jobs_not_allocated += 1;
            continue;
        }

        int current_completion_time = start + job.processing_slots;
        sum_tardiness += std::max(0, current_completion_time - job.due_date_slot);
        prev_idx = current_idx;
        sum_completion_time += current_completion_time;
        last_completion_time = current_completion_time;
    }

    return sum_tardiness + weight_not_allocated * sum_jobs_not_allocated + epsilon * sum_completion_time;
}
