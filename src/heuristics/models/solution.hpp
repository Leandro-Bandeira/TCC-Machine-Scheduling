#pragma once

#include <cmath>
#include <vector>
#include "job.hpp"

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
    double objective_function = MAXFLOAT;
};
