#include "read_instance.hpp"
#include <fstream>
#include <unordered_map>

ProblemData ReadInstance::readData(const std::string& path, const int id_machine) {
    std::ifstream file(path);
    json data = json::parse(file);
    std::vector<Job> jobs = parse_jobs(data, id_machine);
    std::vector<std::vector<int>> setup_matrix = parse_setups(data, id_machine, jobs);
    int H = parse_H(data, id_machine);
    int first_slot = parse_first_slot(data, id_machine);
    std::vector<int> start_slots = parse_start_slots(data, id_machine);
    return ProblemData(jobs, setup_matrix, H, first_slot, start_slots);
}

std::vector<Job> ReadInstance::parse_jobs(const json& data, const int id_machine) {
    std::vector<Job> jobs;
    // Dummy na posição 0: setup_matrix[0][j] = 0 para todo j (sem setup antes do primeiro job)
    jobs.emplace_back(0, 0, 0, 0, 0, 0);
    int idx = 1;
    for(const auto& job_data : data["jobs"]) {
        if(job_data["assigned_machine_id"].get<int>() != id_machine) continue;
        // Ignora jobs já processados — não entram no sequenciamento
        if(job_data["Status_Processed"].get<std::string>() != "") continue;
        jobs.emplace_back(
            job_data["id"].get<int>(),
            job_data["processing_slots"].get<int>(),
            job_data["release_date_slot"].get<int>(),
            job_data["due_date_slot"].get<int>(),
            job_data["resource_id"].get<int>(),
            idx++
        );
    }
    return jobs;
}

// H é o último start_slot disponível — define o horizonte máximo de alocação.
int ReadInstance::parse_H(const json& data, const int id_machine) {
    for (const auto& machine : data["machines"]) {
        if (machine["machine_id"].get<int>() != id_machine) continue;
        const auto& slots = machine["start_slots"];
        if (slots.empty()) return 0;
        return slots.back().get<int>();
    }
    return 0;
}

// first_slot é a abertura do turno — nenhum job pode iniciar antes desse slot.
int ReadInstance::parse_first_slot(const json& data, const int id_machine) {
    for (const auto& machine : data["machines"]) {
        if (machine["machine_id"].get<int>() != id_machine) continue;
        const auto& slots = machine["start_slots"];
        if (slots.empty()) return 0;
        return slots.front().get<int>();
    }
    return 0;
}

std::vector<int> ReadInstance::parse_start_slots(const json& data, const int id_machine) {
    for (const auto& machine : data["machines"]) {
        if (machine["machine_id"].get<int>() != id_machine) continue;
        std::vector<int> slots;
        for (const auto& s : machine["start_slots"]) {
            slots.push_back(s.get<int>());
        }
        return slots;
    }
    return {};
}

// Constrói a matriz de setup a partir do JSON. O campo "setups" tem estrutura:
//   setups[machine_id][job_i_id][job_j_id] = slots_de_setup
// Jobs sem entrada explícita ficam com setup=0 (inicialização da matriz).
std::vector<std::vector<int>> ReadInstance::parse_setups(
    const json& data, const int id_machine, const std::vector<Job>& jobs)
{
    int N = jobs.size();
    std::vector<std::vector<int>> matrix(N, std::vector<int>(N, 0));

    // Mapeia job_id (externo) → idx interno para indexar a matriz
    std::unordered_map<int, int> id_to_idx;
    for (const auto& job : jobs) {
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
