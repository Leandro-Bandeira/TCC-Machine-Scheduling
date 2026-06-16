#pragma once


#include <vector>
#include "job.hpp"


class ProblemData{
    public:
        ProblemData(std::vector<Job> jobs) : jobs(jobs) {}

        // Estamos retornando uma referência constante para evitar modificações externas
        // Retornar uma referência constante permite que o usuário acesse os dados sem a necessidade de copiá-los
        // Referência é basicamente um alias, estamos trabalhando na memória original
        const std::vector<Job>& getJobs() const {return jobs;};
    private:
        std::vector<Job> jobs;
};
