#pragma once
#include "../models/ProblemData.hpp"
#include "../models/solution.hpp"

class ILS{
    public:
        ILS(const ProblemData& problem_data)
        :problem_data(problem_data) {}
        void construction();
        void algorithm();
    private:
        const ProblemData& problem_data;
        Solution solution;
};
