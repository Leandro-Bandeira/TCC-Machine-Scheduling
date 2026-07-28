#pragma once
#include "../models/solution.hpp"
#include "../models/ProblemData.hpp"

// Avalia todas as rotas da solução e retorna a FO total (soma das FOs parciais).
double evaluate(Solution& solution, const ProblemData& problem_data);

// Avalia a rota m no estado atual (chamador já aplicou o movimento antes de
// chamar), sem mutar nada global — as outras rotas usam custo/bits já
// calculados. Ver objective.cpp para detalhes e pré-condições.
double evaluateIntraRoute(Solution& solution, const ProblemData& problem_data, int m);

// Avalia as rotas m e l no estado atual (chamador já aplicou o movimento entre
// as duas rotas antes de chamar), sem mutar nada global. Ver objective.cpp.
double evaluateInterRoute(Solution& solution, const ProblemData& problem_data, int m, int l);
