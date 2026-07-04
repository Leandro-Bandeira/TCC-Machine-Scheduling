#include "objective.hpp"
#include "../models/job.hpp"
#include <algorithm>

// Avalia todas as rotas da solução e retorna a FO total.
//
// Para cada rota, para cada job (ignorando dummies idx=0):
//   1. earliest = max(last_completion + setup, release_date, first_slot)
//   2. Snapa para o menor start_slot >= earliest
//   3. start > H → job não alocado (penalidade W)
//
// FO total = soma das FOs de cada rota individualmente.
double evaluate(const Solution& solution, const ProblemData& problem_data) {
    const std::vector<std::vector<int>>& setup_matrix = problem_data.getSetupMatrix();
    const int H = problem_data.getH();
    const int first_slot = problem_data.getFirstSlot();
    const int numJobs = problem_data.getNumJobs() - 1;
    const std::vector<int>& start_slots = problem_data.getStartSlots();
    const double weight_not_allocated = numJobs * H + 1;
    const double epsilon = 1.0 / weight_not_allocated;

    double total = 0.0;

    for (const auto& route : solution.routes) {
        int sum_tardiness = 0;
        int sum_jobs_not_allocated = 0;
        int sum_completion_time = 0;
        int last_completion_time = 0;
        int prev_idx = 0;

        for (const Job& job : route) {
            if (job.idx == 0) continue;

            int current_idx = job.idx;
            int setup = prev_idx ? setup_matrix[prev_idx][current_idx] : 0;

            int earliest = std::max({last_completion_time + setup, job.release_date_slot, first_slot});

            auto it = std::lower_bound(start_slots.begin(), start_slots.end(), earliest);
            int start = (it != start_slots.end()) ? *it : H + 1;

            if (start > H) {
                sum_jobs_not_allocated += 1;
                continue;
            }

            int current_completion_time = start + job.processing_slots;
            sum_tardiness += std::max(0, current_completion_time - job.due_date_slot);
            prev_idx = current_idx;
            sum_completion_time += current_completion_time;
            last_completion_time = current_completion_time;
        }

        total += sum_tardiness + weight_not_allocated * sum_jobs_not_allocated + epsilon * sum_completion_time;
    }

    return total;
}
