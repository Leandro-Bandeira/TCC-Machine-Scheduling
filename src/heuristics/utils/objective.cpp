#include "objective.hpp"
#include "../models/job.hpp"
#include "utils.hpp"
#include <algorithm>
#include <iostream>

// Núcleo compartilhado por evaluate()/evaluateIntraRoute/evaluateInterRoute:
// percorre uma rota, calcula tardiness/não-alocados/completion, e preenche os
// bits de big_setup via getBits(resource_idx) — genérico o bastante pra servir
// tanto pro bucket real (solution.resource_route_bits[r][rota]) quanto pro
// buffer de trial (solution.trial_bits[r]), sem duplicar o loop de jobs.
//
// write_job_fields controla se job.start/job.end são gravados de verdade:
// true em evaluate() (commit real), false nas versões *Route (são só
// simulação/candidato, não podem mutar o job de verdade até o movimento
// vencedor ser aplicado).
template <typename BitsAccessor>
static double computeRoute(std::vector<Job>& route, const ProblemData& problem_data, BitsAccessor getBits,
                            std::vector<bool>& seen, std::vector<int>& touched, bool write_job_fields, int& out_allocated_jobs) {
    const std::vector<std::vector<int>>& setup_matrix = problem_data.getSetupMatrix();
    const int H = problem_data.getH();
    const int first_slot = problem_data.getFirstSlot();
    const int big_setup = problem_data.getBigSetup();
    const int count_machines = problem_data.getCountMachines();
    const std::vector<int>& next_start_slots = problem_data.getNextStartSlots();
    const double epsilon = problem_data.getEpsilon();

    double sum_tardiness = 0.0, sum_completion_time = 0.0;
    int last_completion_time = 0, prev_idx = 0;
    out_allocated_jobs = 0;

    for (Job& job : route) {
        if (job.idx == 0) continue;

        int setup = prev_idx ? setup_matrix[prev_idx][job.idx] : 0;
        int earliest = std::max({last_completion_time + setup, job.release_date_slot, first_slot});
        int start = (earliest <= H) ? next_start_slots[earliest] : H + 1;

        if (start > H) {
            if (write_job_fields) { job.start = -1; job.end = -1; }
            continue;
        }

        int end = start + job.processing_slots;
        if (write_job_fields) { job.start = start; job.end = end; }

        out_allocated_jobs += 1;
        sum_tardiness += std::max(0, end - job.due_date_slot);
        prev_idx = job.idx;
        sum_completion_time += end;
        last_completion_time = end;
        /*
         * Para o recurso de job, inicio e fim + big setup, coloca em 1 na matriz tridimensional 
         * Marcamos como visto e tocado
         */
        if (count_machines > 1) {
            set_range(getBits(job.resource_idx), start, std::min(H + 1, end + big_setup));
            if (!seen[job.resource_idx]) {
                seen[job.resource_idx] = true;
                touched.push_back(job.resource_idx);
            }
        }
    }

    return sum_tardiness + epsilon * sum_completion_time;
}

// Devolve o buffer ao estado zerado, só nas entradas que foram tocadas.
static void clearTrialBuffer(std::vector<std::vector<uint64_t>>& bits, std::vector<bool>& seen,
                              std::vector<int>& touched) {
    for (int r : touched) {
        std::fill(bits[r].begin(), bits[r].end(), 0ULL);
        seen[r] = false;
    }
    touched.clear();
}

// Conta a quantidade exata de pares de rotas (k1 < k2) que violam a restrição de recurso r.
template <typename BitsAccessor>
static int countResourceViolations(int num_resources, int count_machines, BitsAccessor getBits) {
    if (count_machines <= 1) return 0;
    int violations = 0;
    for (int r = 0; r < num_resources; r++) {
        for (int k1 = 0; k1 < count_machines; k1++) {
            const std::vector<uint64_t>& a = getBits(r, k1);
            for (int k2 = k1 + 1; k2 < count_machines; k2++) {
                const std::vector<uint64_t>& b = getBits(r, k2);
                for (size_t w = 0; w < a.size(); w++) {
                    if (a[w] & b[w]) {
                        violations++;
                        break; // Próximo par (k1, k2) para o recurso r
                    }
                }
            }
        }
    }
    return violations;
}

// Avalia todas as rotas da solução e retorna a FO total.
double evaluate(Solution& solution, const ProblemData& problem_data) {
    const int count_machines = problem_data.getCountMachines();
    const int num_resources = problem_data.getNumResources();
    const double resource_violation_penalty = problem_data.getResourceViolationPenalty();

    double total = 0.0;
    int total_allocated = 0;

    for (int m = 0; m < (int)solution.routes.size(); m++) {
        auto& route = solution.routes[m];
        RouteCache& cache = solution.route_caches[m];

        if (!cache.is_dirty) {
            total += cache.cost;
            total_allocated += cache.allocated_jobs;
            continue;
        }

        if (count_machines > 1) {
            for (int r : cache.touched_resources) {
                auto& bucket = solution.resource_route_bits[r][m];
                std::fill(bucket.begin(), bucket.end(), 0ULL);
            }
        }

        std::vector<bool> seen(count_machines > 1 ? num_resources : 0, false);
        std::vector<int> new_touched;

        cache.cost = computeRoute(
            route, problem_data,
            [&](int r) -> std::vector<uint64_t>& { return solution.resource_route_bits[r][m]; }, seen,
            new_touched, true, cache.allocated_jobs);
        cache.is_dirty = false;

        if (count_machines > 1) cache.touched_resources = std::move(new_touched);

        total += cache.cost;
        total_allocated += cache.allocated_jobs;
    }

    int total_jobs = problem_data.getNumJobs() - 1;
    int unallocated = total_jobs - total_allocated;
    total += unallocated * problem_data.getWeightNotAllocated();

    if (count_machines > 1) {
        int violations = countResourceViolations(num_resources, count_machines,
            [&](int r, int k) -> const std::vector<uint64_t>& {
                return solution.resource_route_bits[r][k];
            });
        total += violations * resource_violation_penalty;
    }

    return total;
}

double evaluateIntraRoute(Solution& solution, const ProblemData& problem_data, int m) {
    const int count_machines = problem_data.getCountMachines();
    const int num_resources = problem_data.getNumResources();
    const double resource_violation_penalty = problem_data.getResourceViolationPenalty();

    double total = 0.0;
    int total_allocated = 0;
    for (int k = 0; k < (int)solution.routes.size(); k++) {
        if (k != m) {
            total += solution.route_caches[k].cost;
            total_allocated += solution.route_caches[k].allocated_jobs;
        }
    }

    int alloc_m = 0;
    total += computeRoute(
        solution.routes[m], problem_data,
        [&](int resource_idx) -> std::vector<uint64_t>& { return solution.trial_bits[resource_idx]; }, solution.trial_seen,
        solution.trial_touched, false, alloc_m);
    total_allocated += alloc_m;

    int total_jobs = problem_data.getNumJobs() - 1;
    int unallocated = total_jobs - total_allocated;
    total += unallocated * problem_data.getWeightNotAllocated();

    if (count_machines > 1) {
        int violations = countResourceViolations(num_resources, count_machines,
            [&](int r, int k) -> const std::vector<uint64_t>& {
                return (k == m) ? solution.trial_bits[r] : solution.resource_route_bits[r][k];
            });
        clearTrialBuffer(solution.trial_bits, solution.trial_seen, solution.trial_touched);
        total += violations * resource_violation_penalty;
    }

    return total;
}

double evaluateInterRoute(Solution& solution, const ProblemData& problem_data, int m, int l) {
    const int count_machines = problem_data.getCountMachines();
    const int num_resources = problem_data.getNumResources();
    const double resource_violation_penalty = problem_data.getResourceViolationPenalty();
    
    double total = 0.0;
    int total_allocated = 0;
    for (int k = 0; k < (int)solution.routes.size(); k++) {
        if (k != m && k != l) {
            total += solution.route_caches[k].cost;
            total_allocated += solution.route_caches[k].allocated_jobs;
        }
    }

    int alloc_m = 0, alloc_l = 0;
    total += computeRoute(
        solution.routes[m], problem_data,
        [&](int resource_idx) -> std::vector<uint64_t>& { return solution.trial_bits[resource_idx]; }, solution.trial_seen,
        solution.trial_touched, false, alloc_m);
    total_allocated += alloc_m;

    total += computeRoute(
        solution.routes[l], problem_data,
        [&](int resource_idx) -> std::vector<uint64_t>& { return solution.trial_bits2[resource_idx]; }, solution.trial_seen2,
        solution.trial_touched2, false, alloc_l);
    total_allocated += alloc_l;

    int total_jobs = problem_data.getNumJobs() - 1;
    int unallocated = total_jobs - total_allocated;
    total += unallocated * problem_data.getWeightNotAllocated();

    if (count_machines > 1) {
        int violations = countResourceViolations(num_resources, count_machines,
            [&](int r, int k) -> const std::vector<uint64_t>& {
                if (k == m) return solution.trial_bits[r];
                if (k == l) return solution.trial_bits2[r];
                return solution.resource_route_bits[r][k];
            });
        clearTrialBuffer(solution.trial_bits, solution.trial_seen, solution.trial_touched);
        clearTrialBuffer(solution.trial_bits2, solution.trial_seen2, solution.trial_touched2);
        total += violations * resource_violation_penalty;
    }

    return total;
}
