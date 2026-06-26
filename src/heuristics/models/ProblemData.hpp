#pragma once


#include <vector>
#include "job.hpp"


class ProblemData{
    public:
        ProblemData(std::vector<Job> jobs, std::vector<std::vector<int>> setup_matrix, int H, int first_slot, std::vector<int> start_slots)
            : jobs(jobs), setup_matrix(setup_matrix), H(H), first_slot(first_slot), start_slots(start_slots) {}

        const std::vector<Job>& getJobs() const { return jobs; }
        const std::vector<std::vector<int>>& getSetupMatrix() const { return setup_matrix; }
        const std::vector<int>& getStartSlots() const { return start_slots; }
        int getH() const { return H; }
        int getFirstSlot() const { return first_slot; }
        int getNumJobs() const { return jobs.size(); }

    private:
        std::vector<Job> jobs;
        std::vector<std::vector<int>> setup_matrix;
        std::vector<int> start_slots;
        int H;
        int first_slot;
};
