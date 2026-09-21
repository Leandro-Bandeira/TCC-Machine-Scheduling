#pragma once
#include <algorithm>
#include "../models/ProblemData.hpp"
#include "../models/solution.hpp"

// Iterated Local Search (ILS) para o problema de sequenciamento em máquinas paralelas.
//
// Fluxo principal:
//   1. construction() — gera solução inicial via GRASP, distribuindo jobs em count_machines rotas
//   2. algorithm()    — chama construction() e aplica busca local (VNS)
//
// A solução contém uma rota por lane (sub-máquina). A FO total é a soma das FOs de cada rota.
// A solução é mantida como membro para evitar cópias desnecessárias entre fases.
class ILS{
    public:
        ILS(const ProblemData& problem_data, int maxIter = 50, int maxIterILS = -1)
        :problem_data(problem_data), m_maxIter(maxIter) {
            int n_jobs = problem_data.getNumJobs() - 1; // excluindo dummy idx=0
            if (maxIterILS > 0) {
                m_maxIterILS = maxIterILS;
            } else {
                m_maxIterILS = (n_jobs >= 150) ? (n_jobs / 2) : std::max(1, n_jobs);
            }
        }

        // Constrói solução inicial usando GRASP: agrupa jobs por release_date, sorteia uma rota
        // aleatória para cada job, ordena candidatos por setup crescente em relação ao último
        // job daquela rota, e seleciona aleatoriamente dentro de uma RCL.
        Solution construction();
        Solution perturbation(Solution solution);
        // Executa o algoritmo completo: construção + busca local VNS.
        void algorithm();

    private:
        const ProblemData& problem_data; // dados da instância (somente leitura)
        Solution solution;               // solução corrente, modificada in-place pelas fases
        int m_maxIter = 50;
        int m_maxIterILS = 10;
};
