#pragma once


#include <vector>
#include "job.hpp"


class ProblemData{
    public:
        ProblemData(std::vector<Job> jobs, std::vector<std::vector<int>> setup_matrix)
            : jobs(jobs), setup_matrix(setup_matrix) {}

        const std::vector<Job>& getJobs() const { return jobs; }
        const std::vector<std::vector<int>>& getSetupMatrix() const { return setup_matrix; }

    private:
        std::vector<Job> jobs;
        std::vector<std::vector<int>> setup_matrix;
};
