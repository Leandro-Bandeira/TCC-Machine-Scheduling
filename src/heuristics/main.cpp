#include <iostream>
#include <chrono>
#include "utils/read_instance.hpp"
#include "models/job.hpp"
#include "models/ProblemData.hpp"
#include "models/solution.hpp"
#include "algorithms/ils.hpp"
#include <memory>
#include <vector>

int main(int argc, char** argv){
    /*  Primeiro argumento é o path para o arquivo de instância(Input.json), segundo é o id da máquina a ser usada */
    // Podemos testar com a instancia 25112025, machine_id 2, coldboxgasado coldbox4
    int machine_to_use = std::stoi(argv[2]);
    ProblemData data = ReadInstance::readData(argv[1], machine_to_use);
    const std::vector<Job>& jobs = data.getJobs();
    const std::vector<std::vector<int>>& matrix = data.getSetupMatrix();
    int N = jobs.size();
    std::cout << "\nSetup matrix (" << N << "x" << N << "):\n";
    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j++) {
            std::cout << matrix[i][j] << " ";
        }
        std::cout << "\n";
    }
    ILS ils(data);
    auto t0 = std::chrono::steady_clock::now();
    ils.algorithm();
    auto t1 = std::chrono::steady_clock::now();
    double elapsed = std::chrono::duration<double>(t1 - t0).count();
    std::cout << "Tempo total: " << elapsed << "s" << std::endl;
    return 0;
}
