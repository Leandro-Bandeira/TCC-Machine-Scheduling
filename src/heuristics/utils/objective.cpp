#include "objective.hpp"
#include "../models/job.hpp"
#include "utils.hpp"
#include <algorithm>

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
                            std::vector<bool>& seen, std::vector<int>& touched, bool write_job_fields) {
    const std::vector<std::vector<int>>& setup_matrix = problem_data.getSetupMatrix();
    const int H = problem_data.getH();
    const int first_slot = problem_data.getFirstSlot();
    const int big_setup = problem_data.getBigSetup();
    const int count_machines = problem_data.getCountMachines();
    const std::vector<int>& next_start_slots = problem_data.getNextStartSlots();
    const double weight_not_allocated = problem_data.getWeightNotAllocated();
    const double epsilon = problem_data.getEpsilon();

    int sum_tardiness = 0, sum_jobs_not_allocated = 0, sum_completion_time = 0;
    int last_completion_time = 0, prev_idx = 0;

    for (Job& job : route) {
        if (job.idx == 0) continue;

        int setup = prev_idx ? setup_matrix[prev_idx][job.idx] : 0;
        int earliest = std::max({last_completion_time + setup, job.release_date_slot, first_slot});
        int start = (earliest <= H) ? next_start_slots[earliest] : H + 1;

        if (start > H) {
            if (write_job_fields) { job.start = -1; job.end = -1; }
            sum_jobs_not_allocated += 1;
            continue;
        }

        int end = start + job.processing_slots;
        if (write_job_fields) { job.start = start; job.end = end; }

        sum_tardiness += std::max(0, end - job.due_date_slot);
        prev_idx = job.idx;
        sum_completion_time += end;
        last_completion_time = end;

        if (count_machines > 1) {
            set_range(getBits(job.resource_idx), start, std::min(H + 1, end + big_setup));
            if (!seen[job.resource_idx]) {
                seen[job.resource_idx] = true;
                touched.push_back(job.resource_idx);
            }
        }
    }

    return sum_tardiness + weight_not_allocated * sum_jobs_not_allocated + epsilon * sum_completion_time;
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

// Checa se os bits tocados de um buffer batem contra outra rota já commitada
// (solution.resource_route_bits[r][k]) e soma a penalidade.
static void checkAgainstCommitted(Solution& solution, const std::vector<std::vector<uint64_t>>& bits,
                                   const std::vector<int>& touched, int skip_k1, int skip_k2,
                                   int count_machines, double weight_not_allocated, double& total) {
    for (int r : touched) {
        const std::vector<uint64_t>& a = bits[r];
        for (int k = 0; k < count_machines; k++) {
            if (k == skip_k1 || k == skip_k2) continue;
            const std::vector<uint64_t>& b = solution.resource_route_bits[r][k];
            bool overlap = false;
            for (size_t w = 0; w < a.size(); w++) {
                if (a[w] & b[w]) { overlap = true; break; }
            }
            if (overlap) { total += weight_not_allocated; break; }
        }
    }
}

// Avalia todas as rotas da solução e retorna a FO total.
//
// Cache por rota (solution.route_caches): se a rota não foi invalidada desde a
// última chamada (is_dirty == false), reaproveita cost em O(1) em vez de
// refazer o loop de jobs — só rotas efetivamente alteradas por um movimento de
// LocalSearch/perturbação são recalculadas.
//
// Após avaliar todas as rotas, verifica a restrição de big_setup cross-rota:
// jobs com mesmo resource_id em rotas diferentes devem ter gap >= big_setup.
//
// Implementação via bucket bitset (solution.resource_route_bits[resource_idx][rota]):
// cada bucket agrega (OR) a ocupação + zona de exclusão [start, end+big_setup)
// de TODOS os jobs daquele resource_id naquela rota. Dois jobs de rotas
// diferentes violam a restrição sse os buckets das duas rotas se sobrepõem em
// alguma posição (AND != 0) — estender só pra frente, em todo job, já cobre
// violação nas duas direções (quem termina primeiro "invade" o início do
// outro, e vice-versa). A Fase 1 já percorre (rota, job) pra calcular
// start/end — atualiza o bucket correspondente ali mesmo, sem custo extra de
// descobrir "qual rota" (m já é a variável do loop). A Fase 2 não escaneia
// job nenhum: só itera os buckets (R x count_machines, pequeno e fixo).
double evaluate(Solution& solution, const ProblemData& problem_data) {
    const int count_machines = problem_data.getCountMachines();
    const int num_resources = problem_data.getNumResources();
    const int num_words = problem_data.getNumWords();
    const double weight_not_allocated = problem_data.getWeightNotAllocated();

    // route_caches pode estar vazio/desalinhado (solução recém-construída ou
    // recém-copiada sem inicialização explícita) — realinha e marca tudo sujo.
    if (solution.route_caches.size() != solution.routes.size())
        solution.route_caches.assign(solution.routes.size(), RouteCache{});

    // resource_route_bits[r][k] precisa cobrir até H + big_setup (zona de
    // exclusão pra frente do último slot possível). Realinha se o tamanho não
    // bater (solução nova/copiada) — zera tudo, força recálculo via is_dirty.
    if (count_machines > 1 &&
        (solution.resource_route_bits.size() != (size_t)num_resources ||
         (num_resources > 0 &&
          (solution.resource_route_bits[0].size() != (size_t)count_machines ||
           solution.resource_route_bits[0][0].size() != (size_t)num_words)))) {
        solution.resource_route_bits.assign(
            num_resources,
            std::vector<std::vector<uint64_t>>(count_machines, std::vector<uint64_t>(num_words, 0ULL)));
    }

    double total = 0.0;

    for (int m = 0; m < (int)solution.routes.size(); m++) {
        auto& route = solution.routes[m];
        RouteCache& cache = solution.route_caches[m];

        // Cache hit: rota não mudou desde a última avaliação — reaproveita em O(1).
        // Os buckets de resource_route_bits que essa rota contribui também não
        // mudaram (rota não tocada), não precisa mexer neles.
        if (!cache.is_dirty) {
            total += cache.cost;
            continue;
        }

        // Antes de recalcular, zera só os buckets que essa rota tocou da ÚLTIMA
        // vez (cache.touched_resources — lista pequena, deduplicada). Não dá pra
        // usar os jobs ATUAIS da rota pra saber o que limpar: se um job SAIU da
        // rota (moveu pra outra), ele não aparece mais no loop, mas o bit antigo
        // dele continua marcado — só a lista salva da vez anterior sabe disso.
        if (count_machines > 1) {
            for (int r : cache.touched_resources) {
                auto& bucket = solution.resource_route_bits[r][m];
                std::fill(bucket.begin(), bucket.end(), 0ULL);
            }
        }

        // Cache miss: rota foi invalidada (movimento a alterou) — recalcula do zero.
        // Monta a lista NOVA de resources tocados (deduplicada via 'seen', R é
        // pequeno) — substitui cache.touched_resources ao final, pra próxima vez.
        std::vector<bool> seen(count_machines > 1 ? num_resources : 0, false);
        std::vector<int> new_touched;

        cache.cost = computeRoute(
            route, problem_data,
            [&](int r) -> std::vector<uint64_t>& { return solution.resource_route_bits[r][m]; }, seen,
            new_touched, /*write_job_fields=*/true);
        cache.is_dirty = false;

        if (count_machines > 1) cache.touched_resources = std::move(new_touched);

        total += cache.cost;
    }

    // Só verifica big_setup se há mais de uma rota (restrição cross-rota).
    // Não escaneia job nenhum: só os buckets (R x count_machines, pequeno).
    if (count_machines > 1) {
        for (int r = 0; r < num_resources; r++) {
            const auto& per_route = solution.resource_route_bits[r];
            bool violated = false;

            for (int k1 = 0; k1 < count_machines && !violated; k1++) {
                for (int k2 = k1 + 1; k2 < count_machines; k2++) {
                    const std::vector<uint64_t>& a = per_route[k1];
                    const std::vector<uint64_t>& b = per_route[k2];

                    bool overlap = false;
                    for (size_t w = 0; w < a.size(); w++) {
                        if (a[w] & b[w]) { overlap = true; break; }
                    }

                    if (overlap) {
                        total += weight_not_allocated;
                        violated = true;
                        break;
                    }
                }
            }
        }
    }

    return total;
}

// Avalia a rota m no estado ATUAL de solution.routes[m] (o chamador já aplicou
// o movimento — swap/reverse/reinserção — antes de chamar), sem mutar nada
// global (job.start/end reais, resource_route_bits, route_caches). Só a rota m
// muda nesse movimento — as outras usam custo já calculado (cache), sem
// recomputar. Serve pra escanear candidatos em Swap/2-Opt/OrOpt sem o vaivém
// de snapshot/restore que causava bit órfão.
//
// Pré-condição: route_caches e resource_route_bits das rotas != m precisam
// estar em dia (chamar evaluate() uma vez antes de começar a escanear
// candidatos garante isso).
double evaluateIntraRoute(Solution& solution, const ProblemData& problem_data, int m) {
    const int count_machines = problem_data.getCountMachines();
    const double weight_not_allocated = problem_data.getWeightNotAllocated();

    double total = 0.0;
    for (int k = 0; k < (int)solution.routes.size(); k++)
        if (k != m) total += solution.route_caches[k].cost;

    total += computeRoute(
        solution.routes[m], problem_data,
        [&](int r) -> std::vector<uint64_t>& { return solution.trial_bits[r]; }, solution.trial_seen,
        solution.trial_touched, /*write_job_fields=*/false);

    if (count_machines > 1) {
        checkAgainstCommitted(solution, solution.trial_bits, solution.trial_touched, m, m, count_machines,
                               weight_not_allocated, total);
        clearTrialBuffer(solution.trial_bits, solution.trial_seen, solution.trial_touched);
    }

    return total;
}

// Avalia as rotas m e l no estado ATUAL de solution.routes (o chamador já
// aplicou o movimento — troca/reinserção entre as duas rotas — antes de
// chamar), sem mutar nada global. Só m e l mudam nesse movimento — as outras
// usam custo já calculado (cache). Precisa de dois buffers de bits (m e l),
// já que uma pode violar contra a outra além de violar contra o resto.
double evaluateInterRoute(Solution& solution, const ProblemData& problem_data, int m, int l) {
    const int count_machines = problem_data.getCountMachines();
    const double weight_not_allocated = problem_data.getWeightNotAllocated();

    double total = 0.0;
    for (int k = 0; k < (int)solution.routes.size(); k++)
        if (k != m && k != l) total += solution.route_caches[k].cost;

    total += computeRoute(
        solution.routes[m], problem_data,
        [&](int r) -> std::vector<uint64_t>& { return solution.trial_bits[r]; }, solution.trial_seen,
        solution.trial_touched, /*write_job_fields=*/false);
    total += computeRoute(
        solution.routes[l], problem_data,
        [&](int r) -> std::vector<uint64_t>& { return solution.trial_bits2[r]; }, solution.trial_seen2,
        solution.trial_touched2, /*write_job_fields=*/false);

    if (count_machines > 1) {
        // m contra l: só entra em jogo se as duas realmente tocam o mesmo resource.
        for (int r : solution.trial_touched) {
            if (!solution.trial_seen2[r]) continue;
            const std::vector<uint64_t>& a = solution.trial_bits[r];
            const std::vector<uint64_t>& b = solution.trial_bits2[r];
            bool overlap = false;
            for (size_t w = 0; w < a.size(); w++) {
                if (a[w] & b[w]) { overlap = true; break; }
            }
            if (overlap) total += weight_not_allocated;
        }

        // m e l contra o resto (rotas que não mudaram nesse movimento).
        checkAgainstCommitted(solution, solution.trial_bits, solution.trial_touched, m, l, count_machines,
                               weight_not_allocated, total);
        checkAgainstCommitted(solution, solution.trial_bits2, solution.trial_touched2, m, l, count_machines,
                               weight_not_allocated, total);

        clearTrialBuffer(solution.trial_bits, solution.trial_seen, solution.trial_touched);
        clearTrialBuffer(solution.trial_bits2, solution.trial_seen2, solution.trial_touched2);
    }

    return total;
}
