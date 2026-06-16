#include <iostream>
#include "utils/read_instance.hpp"
#include "models/job.hpp"
#include "models/ProblemData.hpp"
#include <vector>

int main(int argc, char** argv){
    /*  Primeiro argumento é o path para o arquivo de instância, segundo é o id da máquina a ser usada */
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

    return 0;
}
