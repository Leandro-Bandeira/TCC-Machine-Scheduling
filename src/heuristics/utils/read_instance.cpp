#include "read_instance.hpp"
#include <fstream>

ProblemData ReadInstance::readData(const std::string& path, const int id_machine) {
    std::ifstream file(path);
    json data = json::parse(file);
    std::vector<Job> jobs = parse_jobs(data, id_machine);
    return ProblemData(jobs);
}

std::vector<Job> ReadInstance::parse_jobs(const json& data, const int id_machine) {
    std::vector<Job> jobs;
    for(const auto& job_data : data["jobs"]) {
        if(job_data["assigned_machine_id"].get<int>() != id_machine) {
            continue;
        }
        jobs.emplace_back(
            job_data["id"].get<int>(),
            job_data["processing_slots"].get<int>(),
            job_data["release_date_slot"].get<int>(),
            job_data["resource_id"].get<int>()
        );
    }
    return jobs;
}
