#include "objective.hpp"
#include "../models/job.hpp"
#include <algorithm>

double evaluate(const Solution& solution, const ProblemData& problem_data) {
    std::vector<Job> sequence = solution.sequence;
    const std::vector<std::vector<int>>& setup_matrix = problem_data.getSetupMatrix();
    const int H = problem_data.getH();
    const int first_slot = problem_data.getFirstSlot();
    const int numJobs = problem_data.getNumJobs() - 1;
    const std::vector<int>& start_slots = problem_data.getStartSlots();

    int sum_tardiness = 0;
    int sum_jobs_not_allocated = 0;
    double weight_not_allocated = numJobs * H + 1;
    int sum_completion_time = 0;
    double epsilon = 1.0 / weight_not_allocated;

    int last_completion_time = 0;
    int prev_idx = 0;
    for (const Job& job : sequence) {
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

    return sum_tardiness + weight_not_allocated * sum_jobs_not_allocated + epsilon * sum_completion_time;
}
