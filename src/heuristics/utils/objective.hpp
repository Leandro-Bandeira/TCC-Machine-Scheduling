#pragma once
#include "../models/solution.hpp"
#include "../models/ProblemData.hpp"

// Avalia todas as rotas da solução e retorna a FO total (soma das FOs parciais).
double evaluate(const Solution& solution, const ProblemData& problem_data);
