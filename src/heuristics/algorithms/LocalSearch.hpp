#pragma once

#include <vector>
#include "../models/ProblemData.hpp"
#include "../models/solution.hpp"
#include "../utils/objective.hpp"
class LocalSearch{
    public:
        static bool bestImprovementSwap(const ProblemData& problemData, Solution& solution);
        static bool bestImprovementOrOpt(const ProblemData& problemData, Solution& solution);
        static void algorithm(const ProblemData& problemData, Solution& soltuion);
};
