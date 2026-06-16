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
    for(const auto& job: jobs){
        std::cout << "Job " << job.id << " processing_time " << job.processing_slots << " slots and resource " << job.resource_id << std::endl;
    }
    return 0;
}
