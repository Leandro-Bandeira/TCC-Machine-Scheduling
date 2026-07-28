#pragma once

#include <vector>
#include <unordered_map>
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
        ProblemData(std::vector<Job> jobs, std::vector<std::vector<int>> setup_matrix, int H, int first_slot, std::vector<int> start_slots, int count_machine, int big_setup, std::vector<int> next_start_slots)
            : jobs(jobs), setup_matrix(setup_matrix), H(H), first_slot(first_slot), start_slots(start_slots), count_machines(count_machine), big_setup(big_setup), next_start_slots(next_start_slots) {
            buildResourceIdx();
            // Constantes derivadas da instância — calculadas 1x aqui, não a cada
            // chamada de evaluate()/evaluateIntraRoute/evaluateInterRoute.
            weight_not_allocated = (double)(getNumJobs() - 1) * H + 1;
            epsilon = 1.0 / weight_not_allocated;
            num_words = (H + big_setup) / 64 + 2;
        }

        const std::vector<Job>& getJobs() const { return jobs; }
        const std::vector<std::vector<int>>& getSetupMatrix() const { return setup_matrix; }
        const std::vector<int>& getStartSlots() const { return start_slots; }

        int getCountMachines() const { return count_machines; }
        int getBigSetup() const { return big_setup; }
        int getH() const { return H; }
        int getFirstSlot() const { return first_slot; }
        int getNumJobs() const { return jobs.size(); }
        const std::vector<int>& getNextStartSlots() const { return next_start_slots; }

        // Quantidade de resource_id distintos entre os jobs (R) — dimensiona o
        // bucket resource_route_bits[R][count_machines] usado na checagem de
        // big_setup (ver Solution/objective.cpp).
        int getNumResources() const { return num_resources; }

        // Penalidade de job não alocado e seu inverso — sempre os mesmos valores
        // pra uma instância, não precisam ser recalculados (multiplicação +
        // divisão) em toda chamada de evaluate.
        double getWeightNotAllocated() const { return weight_not_allocated; }
        double getEpsilon() const { return epsilon; }

        // Palavras de uint64_t necessárias pra cobrir H + big_setup em
        // resource_route_bits/trial_bits — mesma conta em todo lugar, 1x só.
        int getNumWords() const { return num_words; }

    private:
        std::vector<Job> jobs;
        std::vector<std::vector<int>> setup_matrix;
        std::vector<int> start_slots;
        int H;
        int first_slot;
        int count_machines;
        int big_setup;
        std::vector<int> next_start_slots;
        int num_resources = 0;
        double weight_not_allocated = 0.0;
        double epsilon = 0.0;
        int num_words = 0;

        // Mapeia cada resource_id (podem ser esparsos, tipo 113, 2831, ...) pra
        // um índice denso 0..R-1, gravado direto em job.resource_idx — feito
        // uma única vez aqui, já que resource_id de um job.idx nunca muda.
        void buildResourceIdx() {
            std::unordered_map<int, int> resource_idx_map;
            for (auto& job : jobs) {
                if (job.idx == 0) continue;
                auto it = resource_idx_map.find(job.resource_id);
                if (it == resource_idx_map.end()) {
                    it = resource_idx_map.emplace(job.resource_id, (int)resource_idx_map.size()).first;
                }
                job.resource_idx = it->second;
            }
            num_resources = (int)resource_idx_map.size();
        }
};
