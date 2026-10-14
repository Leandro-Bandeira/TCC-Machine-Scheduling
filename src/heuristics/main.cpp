#include <iostream>
#include <chrono>
#include "utils/read_instance.hpp"
#include "models/job.hpp"
#include "models/ProblemData.hpp"
#include "models/solution.hpp"
#include "algorithms/ils.hpp"
#include <memory>
#include <vector>

// Ponto de entrada da heurística ILS.
// Uso: ./heuristic <path_input.json> <machine_id>
//
// Lê a instância, imprime os dados da instância (N, M, etc.),
// executa o ILS (construção GRASP + VNS) e reporta o tempo total e a melhor solução.
int main(int argc, char** argv){
    if (argc < 3) {
        std::cerr << "Uso: " << argv[0] << " <path_input.json> <machine_id>\n";
        return 1;
    }

    int machine_to_use = std::stoi(argv[2]);
    std::string input_path = argv[1];
    ProblemData data = ReadInstance::readData(input_path, machine_to_use);

    ILS ils(data);
    ils.algorithm(input_path, machine_to_use);
    return 0;
}
