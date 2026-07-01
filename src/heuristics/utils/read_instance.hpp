#pragma once

#include <string>
#include <vector>
#include <nlohmann/json.hpp>
#include "../models/job.hpp"
#include "../models/ProblemData.hpp"

using json = nlohmann::json;

// Lê e parseia o input.json da instância, extraindo apenas os dados
// da máquina especificada por id_machine.
class ReadInstance{
    public:
        // Ponto de entrada: lê o arquivo em `path` e retorna ProblemData completo para a máquina.
        static ProblemData readData(const std::string& path, const int id_machine);

    private:
        // Parseia apenas os jobs atribuídos à máquina e ainda não processados (Status_Processed == "").
        // Insere um dummy job (idx=0) na posição 0 para simplificar cálculo de setup.
        static std::vector<Job> parse_jobs(const json& data, const int id_machine);

        // Constrói a matriz de setup NxN a partir do campo "setups" do JSON.
        // Usa id_to_idx para mapear job_id → índice interno.
        // Pares de jobs não presentes no JSON ficam com setup=0.
        static std::vector<std::vector<int>> parse_setups(const json& data, const int id_machine, const std::vector<Job>& jobs);

        // Retorna o último start_slot da máquina (horizonte H).
        static int parse_H(const json& data, const int id_machine);

        // Retorna o primeiro start_slot da máquina (abertura do turno).
        static int parse_first_slot(const json& data, const int id_machine);

        // Retorna a lista completa de start_slots da máquina em ordem crescente.
        static std::vector<int> parse_start_slots(const json& data, const int id_machine);
};
