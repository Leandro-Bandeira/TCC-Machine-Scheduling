#pragma once

#include <vector>
#include "job.hpp"

// Agrega todos os dados estáticos da instância para uma máquina específica.
// Passado por referência constante para ILS e LocalSearch — nunca modificado.
class ProblemData{
    public:
        // jobs: vetor de jobs da máquina; jobs[0] é sempre o dummy (idx=0).
        // setup_matrix: matrix NxN onde setup_matrix[i][j] é o tempo de setup
        //   em slots necessário após processar o job de idx=i antes do job idx=j.
        // H: último start_slot disponível — horizonte de planejamento.
        // first_slot: primeiro start_slot disponível (abertura do turno).
        // start_slots: lista ordenada de todos os slots em que a máquina pode iniciar
        //   um job (slots de abertura de turno). Jobs só podem começar nesses instantes.
        // count_machines: Número de máquinas em paralela do problema
        ProblemData(std::vector<Job> jobs, std::vector<std::vector<int>> setup_matrix, int H, int first_slot, std::vector<int> start_slots, int count_machine, int big_setup)
            : jobs(jobs), setup_matrix(setup_matrix), H(H), first_slot(first_slot), start_slots(start_slots), count_machines(count_machine), big_setup(big_setup) {}

        const std::vector<Job>& getJobs() const { return jobs; }
        const std::vector<std::vector<int>>& getSetupMatrix() const { return setup_matrix; }
        const std::vector<int>& getStartSlots() const { return start_slots; }
        int getCountMachines() const { return count_machines; }
        int getBigSetup() const { return big_setup; }
        int getH() const { return H; }
        int getFirstSlot() const { return first_slot; }
        int getNumJobs() const { return jobs.size(); }

    private:
        std::vector<Job> jobs;
        std::vector<std::vector<int>> setup_matrix;
        std::vector<int> start_slots;
        int H;
        int first_slot;
        int count_machines;
        int big_setup;
};
