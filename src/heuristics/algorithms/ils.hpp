#pragma once
#include "../models/ProblemData.hpp"
#include "../models/solution.hpp"
#include <memory>


class ILS{
    public:
        ILS(const ProblemData& problem_data)
        :problem_data(problem_data) {}
        std::unique_ptr<Solution> contruction();
        double evaluate(const Solution& solution);
    private:
        const ProblemData& problem_data;
};
