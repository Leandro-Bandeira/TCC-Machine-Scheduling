#include "read_instance.hpp"
#include <fstream>
#include <unordered_map>

ProblemData ReadInstance::readData(const std::string& path, const int id_machine) {
    std::ifstream file(path);
    json data = json::parse(file);
    std::vector<Job> jobs = parse_jobs(data, id_machine);
    std::vector<std::vector<int>> setup_matrix = parse_setups(data, id_machine, jobs);
    return ProblemData(jobs, setup_matrix);
}

std::vector<Job> ReadInstance::parse_jobs(const json& data, const int id_machine) {
    std::vector<Job> jobs;
    int idx = 0;
    for(const auto& job_data : data["jobs"]) {
        if(job_data["assigned_machine_id"].get<int>() != id_machine) {
            continue;
        }
        jobs.emplace_back(
            job_data["id"].get<int>(),
            job_data["processing_slots"].get<int>(),
            job_data["release_date_slot"].get<int>(),
            job_data["resource_id"].get<int>(),
            idx++
        );
    }
    return jobs;
}

std::vector<std::vector<int>> ReadInstance::parse_setups(
    const json& data, const int id_machine, const std::vector<Job>& jobs)
{
    int N = jobs.size();
    std::vector<std::vector<int>> matrix(N, std::vector<int>(N, 0));

    std::unordered_map<int, int> id_to_idx;
    for (const auto& job:jobs) {
        id_to_idx[job.id] = job.idx;
    }

    std::string machine_key = std::to_string(id_machine);
    if (!data["setups"].contains(machine_key)) return matrix;

    for (const auto& [i_str, targets] : data["setups"][machine_key].items()) {
        int job_i_id = std::stoi(i_str);
        if (!id_to_idx.count(job_i_id)) continue;

        for (const auto& [j_str, slots] : targets.items()) {
            int job_j_id = std::stoi(j_str);
            if (!id_to_idx.count(job_j_id)) continue;

            matrix[id_to_idx[job_i_id]][id_to_idx[job_j_id]] = slots.get<int>();
        }
    }
    return matrix;
}
