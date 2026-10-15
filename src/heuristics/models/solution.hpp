#pragma once

#include <cmath>
#include <cstdint>
#include <climits>
#include <utility>
#include <vector>
#include "job.hpp"


/* is_dirty é utilizado para reaproveitamento do custo da rota, caso ela não foi alterado (is_dirty = false)
* Reutilizamos seu custo
*/
struct RouteCache {
    double cost = 0.0;
    int allocated_jobs = 0;
    bool is_dirty = true;
};

// Intervalo de ocupação de um recurso por um job alocado: [s, e), onde
// e = min(H + 1, end + big_setup). k é a rota (máquina) real dona do job.
struct ResourceInterval {
    int s;
    int e;
    int k;
};

// Buffer de intervalos de TESTE de uma rota candidata, agrupados por recurso.
// Cada by_res[r] sai ordenado por início, pois a rota é percorrida em ordem e o
// start dos jobs só cresce ao longo dela. touched guarda os recursos com pelo
// menos um intervalo, para limpar só o que foi usado.
struct TrialIntervals {
    std::vector<std::vector<std::pair<int, int>>> by_res; // (s, e) por recurso
    std::vector<int> touched;

    void init(int num_resources) {
        by_res.assign(num_resources, {});
        touched.clear();
    }

    void add(int resource_idx, int s, int e) {
        if (by_res[resource_idx].empty()) touched.push_back(resource_idx);
        by_res[resource_idx].emplace_back(s, e);
    }

    void clear() {
        for (int r : touched) by_res[r].clear();
        touched.clear();
    }
};

// Representa uma solução completa: count_machines rotas de jobs e o valor da função objetivo.
//
// Cada rota corresponde a um lane (sub-máquina) e começa e termina com um Job dummy
// (idx=0, todos os campos zero). Os sentinelas simplificam o cálculo de setup:
// o setup do primeiro job real é zero (prev_idx=0 → setup_matrix[0][j] = 0).
//
// Estrutura de cada rota: [ dummy | job_a | job_b | ... | dummy ]
// A FO total é a soma das FOs de cada rota avaliadas independentemente.
struct Solution{
    std::vector<std::vector<Job>> routes;
    std::vector<RouteCache> route_caches;
    double objective_function = MAXFLOAT;

    // Conflito de recurso compartilhado (big_setup cross-rota) via intervalos.
    // Ver heuristics_information/resource_conflict_intervals.md.
    //
    // resource_intervals[r]: intervalos de todos os jobs alocados do recurso r em
    // máquinas reais, ordenados por (s, k, e). Só é refeito em evaluate(), quando
    // alguma rota está suja (commit de um movimento aceito, perturbação, construção).
    std::vector<std::vector<ResourceInterval>> resource_intervals;

    // total_violations: nº de pares de máquinas (k1, k2) que violam a restrição de
    // recurso, somado sobre os recursos (cada par conta uma vez por recurso).
    // pair_viol[k1 * M + k2]: em quantos recursos o par (k1, k2) viola (simétrica).
    // row_viol[k]: soma da linha k de pair_viol, ou seja, violações que envolvem k.
    int total_violations = 0;
    std::vector<int> pair_viol;
    std::vector<int> row_viol;

    // Buffers de teste reutilizados nas avaliações de candidatos. trial1 simula a
    // rota m e trial2 a rota l (evaluateInterRoute), pois m e l também são
    // comparadas entre si e não só contra o resto.
    TrialIntervals trial1;
    TrialIntervals trial2;

    // Scratch do sweep: last_end[k] = maior fim já visto da máquina k no recurso
    // corrente; mark_m/mark_l/pair_mark com carimbo evitam contar a mesma máquina
    // (ou o mesmo par) duas vezes no mesmo recurso, sem precisar zerar os vetores.
    std::vector<int> last_end;
    std::vector<uint64_t> mark_m;
    std::vector<uint64_t> mark_l;
    std::vector<uint64_t> pair_mark;
    uint64_t stamp = 0;

    // Marca a rota route_idx como suja: próxima chamada de evaluate() recalcula
    // essa rota do zero em vez de reaproveitar o cache. Precisa ser chamado em
    // TODO ponto que modificar solution.routes[route_idx] diretamente.
    void invalidateRoute(int route_idx) {
        if (route_idx >= 0 && route_idx < (int)route_caches.size())
            route_caches[route_idx].is_dirty = true;
    }

    // Dimensiona/zera route_caches e as estruturas de intervalos de recurso 1x,
    // na criação da solução (chamar logo após construction() montar
    // solution.routes). num_resources/count_machines são constantes
    // da instância — não precisam ser checados a cada chamada de evaluate()/
    // evaluateIntraRoute/evaluateInterRoute. Cópias subsequentes (perturbation,
    // best-tracking em ILS/LocalSearch) herdam esse dimensionamento via cópia
    // de vector, então isso roda uma única vez por instância.
    void initEvalBuffers(int num_resources, int count_machines) {
        /* Para cada vetor de jobs (Rota), inicializa uma RouteCache */
        route_caches.assign(routes.size(), RouteCache{});

        if (count_machines > 1) {
            resource_intervals.assign(num_resources, {});
            total_violations = 0;
            pair_viol.assign((size_t)count_machines * count_machines, 0);
            row_viol.assign(count_machines, 0);
            trial1.init(num_resources);
            trial2.init(num_resources);
            last_end.assign(count_machines, INT_MIN);
            mark_m.assign(count_machines, 0);
            mark_l.assign(count_machines, 0);
            pair_mark.assign((size_t)count_machines * count_machines, 0);
            stamp = 0;
        }
    }
};
