#pragma once
#include "../models/solution.hpp"
#include "../models/ProblemData.hpp"

// Avalia uma solução e retorna o valor da função objetivo composta:
//
//   FO = sum_tardiness + W * jobs_nao_alocados + epsilon * sum_completion_time
//
// onde:
//   W       = n*H + 1         — penalidade dominante: qualquer job alocado é melhor que um não alocado
//   epsilon = 1 / W           — peso de desempate: minimiza completion time total sem interferir no tardiness
//
// Um job não é alocado quando seu start calculado ultrapassa H (horizonte).
// O start de cada job é o menor start_slot >= max(last_completion + setup, release_date, first_slot).
double evaluate(const Solution& solution, const ProblemData& problem_data);
