#pragma once

#include <string>
#include <vector>
#include <nlohmann/json.hpp>
#include "../models/job.hpp"
#include "../models/ProblemData.hpp"

using json = nlohmann::json;

class ReadInstance{
    public:
        static ProblemData readData(const std::string& path, const int id_machine);

    private:
        static std::vector<Job> parse_jobs(const json& data, const int id_machine);

};
