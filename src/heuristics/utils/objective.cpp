#include "objective.hpp"
#include "../models/job.hpp"
#include "utils.hpp"
#include <algorithm>
#include <climits>
#include <cstdlib>
#include <iostream>

// Núcleo compartilhado por evaluate()/evaluateIntraRoute/evaluateInterRoute:
// percorre uma rota, calcula tardiness/não-alocados/completion e, se `trial` não
// for nulo, registra o intervalo de ocupação de recurso de cada job alocado:
//
//     [start, min(H + 1, end + big_setup))
//
// Como a rota é percorrida em ordem e start só cresce ao longo dela, cada
// trial->by_res[r] já sai ordenado por início, sem sort.
//
// write_job_fields controla se job.start/job.end são gravados de verdade:
// true em evaluate() (commit real), false nas versões *Route (são só
// simulação/candidato, não podem mutar o job de verdade até o movimento
// vencedor ser aplicado).
static double computeRoute(std::vector<Job>& route, const ProblemData& problem_data, TrialIntervals* trial,
                            bool write_job_fields, int& out_allocated_jobs, bool is_pool_route) {
    out_allocated_jobs = 0;
    if (is_pool_route) {
        if (write_job_fields) {
            for (Job& job : route) {
                if (job.idx == 0) continue;
                job.start = -1;
                job.end = -1;
            }
        }
        return 0.0;
    }

    const std::vector<std::vector<int>>& setup_matrix = problem_data.getSetupMatrix();
    const int H = problem_data.getH();
    const int first_slot = problem_data.getFirstSlot();
    const int big_setup = problem_data.getBigSetup();
    const int count_machines = problem_data.getCountMachines();
    const std::vector<int>& next_start_slots = problem_data.getNextStartSlots();
    const double epsilon = problem_data.getEpsilon();

    double sum_tardiness = 0.0, sum_completion_time = 0.0;
    int last_completion_time = 0, prev_idx = 0;

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

        // Intervalo de ocupação do recurso do job (início, fim + big setup)
        if (trial && count_machines > 1) {
            trial->add(job.resource_idx, start, std::min(H + 1, end + big_setup));
        }
    }

    return sum_tardiness + epsilon * sum_completion_time;
}

// Refaz resource_intervals, pair_viol, row_viol e total_violations a partir de
// job.start/job.end das rotas reais (que evaluate() acabou de atualizar nas
// rotas sujas). Chamada só quando alguma rota mudou, ou seja, no commit de um
// movimento aceito, na perturbação e na construção. Não é chamada por candidato.
//
// Para cada recurso: ordena os intervalos por (s, k, e) e varre em ordem de
// início mantendo last_end[k] (maior fim já visto da máquina k). Ao chegar um
// intervalo de início s da máquina k, toda outra máquina j com last_end[j] > s
// ainda está ocupando o recurso, contabilizando uma violação para o par (k, j).
static void rebuildResourceIntervals(Solution& sol, const ProblemData& problem_data) {
    const int M = problem_data.getCountMachines();
    const int H = problem_data.getH();
    const int big_setup = problem_data.getBigSetup();

    for (auto& g : sol.resource_intervals) g.clear();
    for (int k = 0; k < M; k++) {
        for (const Job& job : sol.routes[k]) {
            if (job.idx == 0 || job.start < 0) continue; // dummy ou não alocado
            sol.resource_intervals[job.resource_idx].push_back({job.start, std::min(H + 1, job.end + big_setup), k});
        }
    }

    std::fill(sol.pair_viol.begin(), sol.pair_viol.end(), 0);
    std::fill(sol.row_viol.begin(), sol.row_viol.end(), 0);
    sol.total_violations = 0;

    for (auto& g : sol.resource_intervals) {
        if (g.size() < 2) continue;
        std::sort(g.begin(), g.end(), [](const ResourceInterval& a, const ResourceInterval& b) {
            if (a.s != b.s) return a.s < b.s;
            if (a.k != b.k) return a.k < b.k;
            return a.e < b.e;
        });

        std::fill(sol.last_end.begin(), sol.last_end.end(), INT_MIN);
        for (const ResourceInterval& x : g) {
            for (int j = 0; j < M; j++) {
                if (j == x.k || sol.last_end[j] <= x.s) continue;
                size_t a = (size_t)x.k * M + j, b = (size_t)j * M + x.k;
                sol.pair_viol[a]++;
                sol.pair_viol[b]++;
                sol.row_viol[x.k]++;
                sol.row_viol[j]++;
                sol.total_violations++;
            }
            sol.last_end[x.k] = std::max(sol.last_end[x.k], x.e);
        }
    }
}

// Conta as violações de recurso em que a(s) rota(s) candidata(s) participam,
// usando os intervalos de teste (trial1 para mm, trial2 para ll) contra os
// intervalos committed das demais máquinas (resource_intervals sem mm e ll).
//
// mm/ll: rotas reais candidatas, ou -1 se ausente ou se for o pool virtual
// (rota de índice M, jobs não processados, que não ocupa recurso nenhum).
//
// Para cada recurso tocado, faz um merge de até 3 listas ordenadas por (s, k)
// (G sem mm/ll, A = trial de mm, B = trial de ll) mantendo last_end[k]:
//   - intervalo de mm (A): toda outra máquina j (≠ mm, ≠ ll) com last_end[j] > s
//     conflita com mm; se last_end[ll] > s, o par (mm, ll) conflita;
//   - intervalo de ll (B): análogo;
//   - intervalo de outra máquina k (G): se last_end[mm] > s conflita com mm, e
//     se last_end[ll] > s conflita com ll.
// Custo por recurso: O(n_r + (a_r + b_r) * M).
static int trialViolations(Solution& sol, int M, int mm, int ll) {
    const TrialIntervals* tm = (mm >= 0) ? &sol.trial1 : nullptr;
    const TrialIntervals* tl = (ll >= 0) ? &sol.trial2 : nullptr;

    auto process = [&](int r) -> int {
        const std::vector<std::pair<int, int>>* A = (tm && !tm->by_res[r].empty()) ? &tm->by_res[r] : nullptr;
        const std::vector<std::pair<int, int>>* B = (tl && !tl->by_res[r].empty()) ? &tl->by_res[r] : nullptr;
        if (!A && !B) return 0;
        const std::vector<ResourceInterval>& G = sol.resource_intervals[r];
        if (G.empty() && !(A && B)) return 0;

        std::fill(sol.last_end.begin(), sol.last_end.end(), INT_MIN);

        int count = 0;
        size_t ig = 0, ia = 0, ib = 0;

        while (true) {
            while (ig < G.size() && (G[ig].k == mm || G[ig].k == ll)) ig++;
            const bool hasG = ig < G.size();
            const bool hasA = A && ia < A->size();
            const bool hasB = B && ib < B->size();
            if (!hasG && !hasA && !hasB) break;

            // Escolhe a menor cabeça por (s, k), mantendo a mesma ordem do std::sort de rebuildResourceIntervals
            int src = -1, best_s = INT_MAX, best_k = INT_MAX;
            if (hasG) { src = 0; best_s = G[ig].s; best_k = G[ig].k; }
            if (hasA && ((*A)[ia].first < best_s || ((*A)[ia].first == best_s && mm < best_k))) {
                src = 1; best_s = (*A)[ia].first; best_k = mm;
            }
            if (hasB && ((*B)[ib].first < best_s || ((*B)[ib].first == best_s && ll < best_k))) {
                src = 2; best_s = (*B)[ib].first; best_k = ll;
            }

            int s = best_s, e, k;
            if (src == 0) {
                e = G[ig].e; k = G[ig].k; ig++;
                if (mm >= 0 && sol.last_end[mm] > s) count++;
                if (ll >= 0 && sol.last_end[ll] > s) count++;
            } else if (src == 1) {
                e = (*A)[ia].second; k = mm; ia++;
                for (int j = 0; j < M; j++) {
                    if (j == mm || j == ll || sol.last_end[j] <= s) continue;
                    count++;
                }
                if (ll >= 0 && sol.last_end[ll] > s) count++;
            } else {
                e = (*B)[ib].second; k = ll; ib++;
                for (int j = 0; j < M; j++) {
                    if (j == mm || j == ll || sol.last_end[j] <= s) continue;
                    count++;
                }
                if (mm >= 0 && sol.last_end[mm] > s) count++;
            }
            sol.last_end[k] = std::max(sol.last_end[k], e);
        }
        return count;
    };

    int total = 0;
    if (tm) {
        for (int r : tm->touched) total += process(r);
    }
    if (tl) {
        for (int r : tl->touched) {
            if (tm && !tm->by_res[r].empty()) continue; // já processado junto com mm
            total += process(r);
        }
    }
    return total;
}

// Avalia todas as rotas da solução e retorna a FO total.
// Também é o "commit": recalcula as rotas sujas (atualizando job.start/job.end)
// e, se alguma mudou, refaz os intervalos de recurso e o total de violações.
double evaluate(Solution& solution, const ProblemData& problem_data) {
    const int count_machines = problem_data.getCountMachines();
    const double resource_violation_penalty = problem_data.getResourceViolationPenalty();

    double total = 0.0;
    int total_allocated = 0;
    bool any_dirty = false;

    for (int m = 0; m < (int)solution.routes.size(); m++) {
        auto& route = solution.routes[m];
        RouteCache& cache = solution.route_caches[m];
        bool is_pool = (m >= count_machines);

        if (!cache.is_dirty) {
            total += cache.cost;
            total_allocated += cache.allocated_jobs;
            continue;
        }

        any_dirty = true;
        cache.cost = computeRoute(route, problem_data, nullptr, true, cache.allocated_jobs, is_pool);
        cache.is_dirty = false;

        total += cache.cost;
        total_allocated += cache.allocated_jobs;
    }

    int total_jobs = problem_data.getNumJobs() - 1;
    int unallocated = total_jobs - total_allocated;
    total += unallocated * problem_data.getWeightNotAllocated();

    if (count_machines > 1) {
        if (any_dirty) rebuildResourceIntervals(solution, problem_data);
        total += solution.total_violations * resource_violation_penalty;
    }

    return total;
}

#ifdef VERIFY_EVAL
// Verificação (só em build com -DVERIFY_EVAL): recalcula a FO do estado atual
// de solution do zero (todas as rotas sujas) e compara com o valor incremental.
static void verifyAgainstFull(const Solution& solution, const ProblemData& problem_data, double value, const char* tag) {
    Solution c = solution;
    for (int i = 0; i < (int)c.routes.size(); i++) c.invalidateRoute(i);
    double full = evaluate(c, problem_data);
    if (std::fabs(full - value) > 1e-6 * (1.0 + std::fabs(full))) {
        std::cerr << "[VERIFY_EVAL] divergencia em " << tag << ": incremental=" << value << " completo=" << full << std::endl;
        std::abort();
    }
}
#endif

double evaluateIntraRoute(Solution& solution, const ProblemData& problem_data, int m) {
    const int count_machines = problem_data.getCountMachines();
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
    bool is_pool = (m >= count_machines);
    total += computeRoute(solution.routes[m], problem_data, &solution.trial1, false, alloc_m, is_pool);
    total_allocated += alloc_m;

    int total_jobs = problem_data.getNumJobs() - 1;
    int unallocated = total_jobs - total_allocated;
    total += unallocated * problem_data.getWeightNotAllocated();

    if (count_machines > 1) {
        // V_novo = V_total - V_antigo(m) + V_trial(m); o pool virtual não ocupa recurso
        int violations = solution.total_violations;
        if (!is_pool) {
            violations += trialViolations(solution, count_machines, m, -1) - solution.row_viol[m];
        }
        solution.trial1.clear();
        total += violations * resource_violation_penalty;
    }

#ifdef VERIFY_EVAL
    verifyAgainstFull(solution, problem_data, total, "evaluateIntraRoute");
#endif
    return total;
}

double evaluateInterRoute(Solution& solution, const ProblemData& problem_data, int m, int l) {
    const int count_machines = problem_data.getCountMachines();
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
    bool is_pool_m = (m >= count_machines);
    bool is_pool_l = (l >= count_machines);

    total += computeRoute(solution.routes[m], problem_data, &solution.trial1, false, alloc_m, is_pool_m);
    total_allocated += alloc_m;

    total += computeRoute(solution.routes[l], problem_data, &solution.trial2, false, alloc_l, is_pool_l);
    total_allocated += alloc_l;

    int total_jobs = problem_data.getNumJobs() - 1;
    int unallocated = total_jobs - total_allocated;
    total += unallocated * problem_data.getWeightNotAllocated();

    if (count_machines > 1) {
        // Rotas reais candidatas (o pool virtual, índice >= count_machines, não ocupa recurso)
        const int mm = is_pool_m ? -1 : m;
        const int ll = is_pool_l ? -1 : l;

        // Violações antigas que envolvem mm ou ll: o par (mm, ll) aparece nas duas
        // linhas, então é subtraído uma vez para não contar duas vezes.
        int old_violations = 0;
        if (mm >= 0) old_violations += solution.row_viol[mm];
        if (ll >= 0) old_violations += solution.row_viol[ll];
        if (mm >= 0 && ll >= 0) old_violations -= solution.pair_viol[(size_t)mm * count_machines + ll];

        int violations = solution.total_violations - old_violations + trialViolations(solution, count_machines, mm, ll);

        solution.trial1.clear();
        solution.trial2.clear();
        total += violations * resource_violation_penalty;
    }

#ifdef VERIFY_EVAL
    verifyAgainstFull(solution, problem_data, total, "evaluateInterRoute");
#endif
    return total;
}
