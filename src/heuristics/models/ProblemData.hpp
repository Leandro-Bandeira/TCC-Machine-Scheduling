#pragma once


#include <vector>
#include "job.hpp"


class ProblemData{
    public:
        ProblemData(std::vector<Job> jobs, std::vector<std::vector<int>> setup_matrix, int H)
            : jobs(jobs), setup_matrix(setup_matrix), H(H) {}

        const std::vector<Job>& getJobs() const { return jobs; }
        const std::vector<std::vector<int>>& getSetupMatrix() const { return setup_matrix; }
        int getH() const { return H; }
        int getNumJobs() const { return jobs.size(); }

    private:
        std::vector<Job> jobs;
        std::vector<std::vector<int>> setup_matrix;
        int H;
};
