#pragma once

#include <cmath>
#include <cstdint>
#include <vector>
#include "job.hpp"

// Cache do resultado de evaluate() para uma única rota. Enquanto a rota não muda
// (is_dirty == false), evaluate() reaproveita cost em O(1) em vez de recalcular
// a rota inteira do zero a cada chamada.
struct RouteCache {
    double cost = 0.0;
    bool is_dirty = true;

    // resource_idx distintos (sem repetição) que essa rota tocou na última vez
    // que foi recalculada com sucesso. Usado pra limpar só os buckets certos de
    // solution.resource_route_bits antes de recalcular — sem isso, não daria pra
    // saber quais buckets limpar quando um job SAI da rota (ele não aparece mais
    // no loop de jobs atual, mas o bit antigo dele ainda tá marcado).
    std::vector<int> touched_resources;
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

    // Bucket [resource_idx][route] -> bitset agregado (OR de todos os jobs desse
    // resource_id naquela rota, ocupação + zona de exclusão de big_setup). Vive
    // aqui (não em ProblemData) porque muda com a solução — mas resource_idx e
    // rota são dimensões fixas da instância, só o CONTEÚDO dos bits muda.
    // Atualizado durante a Fase 1 de evaluate() (route/resource já disponíveis
    // de graça no loop); checado na Fase 2 sem precisar escanear job nenhum.
    std::vector<std::vector<std::vector<uint64_t>>> resource_route_bits;

    // Scratch de evaluateIntraRoute (objective.cpp): bits temporários da rota
    // sendo simulada, indexados por resource_idx — reutilizados entre chamadas
    // (realinhados só se o tamanho não bater com a instância), sempre limpos de
    // volta a zero no final de cada chamada. trial_seen/trial_touched evitam
    // duplicar entradas e permitem limpar só o que foi tocado, não tudo.
    std::vector<std::vector<uint64_t>> trial_bits;
    std::vector<bool> trial_seen;
    std::vector<int> trial_touched;

    // Segundo buffer, mesmo padrão — usado por evaluateInterRoute pra simular
    // a SEGUNDA rota (l) de movimentos que mexem em duas rotas ao mesmo tempo
    // (SwapInterRoute, Realocate). Precisa de dois buffers simultâneos porque
    // m e l são comparadas uma contra a outra, não só contra o resto.
    std::vector<std::vector<uint64_t>> trial_bits2;
    std::vector<bool> trial_seen2;
    std::vector<int> trial_touched2;

    // Marca a rota route_idx como suja: próxima chamada de evaluate() recalcula
    // essa rota do zero em vez de reaproveitar o cache. Precisa ser chamado em
    // TODO ponto que modificar solution.routes[route_idx] diretamente.
    void invalidateRoute(int route_idx) {
        if (route_idx >= 0 && route_idx < (int)route_caches.size())
            route_caches[route_idx].is_dirty = true;
    }

    // Dimensiona/zera route_caches, resource_route_bits e os buffers de trial
    // 1x, na criação da solução (chamar logo após construction() montar
    // solution.routes). num_resources/num_words/count_machines são constantes
    // da instância — não precisam ser checados a cada chamada de evaluate()/
    // evaluateIntraRoute/evaluateInterRoute. Cópias subsequentes (perturbation,
    // best-tracking em ILS/LocalSearch) herdam esse dimensionamento via cópia
    // de vector, então isso roda uma única vez por instância.
    void initEvalBuffers(int num_resources, int num_words, int count_machines) {
        route_caches.assign(routes.size(), RouteCache{});

        if (count_machines > 1) {
            resource_route_bits.assign(
                num_resources,
                std::vector<std::vector<uint64_t>>(count_machines, std::vector<uint64_t>(num_words, 0ULL)));
            trial_bits.assign(num_resources, std::vector<uint64_t>(num_words, 0ULL));
            trial_seen.assign(num_resources, false);
            trial_bits2.assign(num_resources, std::vector<uint64_t>(num_words, 0ULL));
            trial_seen2.assign(num_resources, false);
        }
    }
};
