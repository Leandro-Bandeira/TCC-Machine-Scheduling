#include "utils.hpp"
#include <iostream>
#include <iomanip>

void printRoutes(const Solution& solution){
    int count_machines = (int)solution.routes.size();
    std::cout << "\n[solução] " << count_machines << " rota(s):\n";
    for(int m = 0; m < count_machines; m++){
        const auto& route = solution.routes[m];
        int real_jobs = (int)route.size() - 2;
        std::cout << "  rota[" << m << "] (" << real_jobs << " jobs): ";
        for(const auto& job : route){
            if(job.idx == 0) { std::cout << "[D]"; continue; }
            std::cout << "[id=" << job.id
                      << " res=" << job.resource_id
                      << " rel=" << job.release_date_slot
                      << " due=" << job.due_date_slot
                      << " start=" << job.start
                      << " end=" << job.end << "]";
        }
        std::cout << "\n";
    }
    std::cout << "Função objetivo: " << std::setprecision(15) << solution.objective_function << "\n";
}
