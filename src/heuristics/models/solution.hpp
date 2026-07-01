#pragma once

#include <vector>
#include "job.hpp"

// Representa uma solução completa: uma permutação de jobs mais o valor da função objetivo.
//
// A sequência sempre começa e termina com um Job dummy (idx=0, todos os campos zero).
// Esses sentinelas simplificam o cálculo de setup: o setup do primeiro job real é zero
// (prev_idx=0 → setup_matrix[0][j] = 0) e a lógica de fronteira do loop não precisa
// tratar o caso especial de início/fim de fila.
//
// Estrutura: [ dummy | job_a | job_b | ... | dummy ]
struct Solution{
    std::vector<Job> sequence = {Job(0,0,0,0,0,0), Job(0,0,0,0,0,0)};
    double objective_function;
};
