#include "utils.hpp"
#include <cstdint>
#include <iostream>
#include <iomanip>
int TAM_WORD = 64;

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

void set_range(std::vector<uint64_t>& bits, int start, int end){
    int first_word = start / TAM_WORD;
    int last_word = (end-1) / TAM_WORD;

    for(int w = first_word; w <= last_word; w++){
        int lo = std::max(start, w * 64) -w * 64;
        int hi = std::min(end, (w + 1) * 64) -w*64;
        uint64_t mask = (hi == 64) ? ~0ULL << lo : ((1ULL << (hi - lo)) - 1) << lo;
        bits[w] |= mask;
    }
}

void unset_range(std::vector<uint64_t>& bits, int start, int end) {
    int first_word = start / 64, last_word = (end - 1) / 64;
    for (int w = first_word; w <= last_word; w++) {
        int lo = std::max(start, w * 64) - w * 64;
        int hi = std::min(end, (w + 1) * 64) - w * 64;
        uint64_t mask = (hi == 64) ? ~0ULL << lo : ((1ULL << (hi - lo)) - 1) << lo;
        bits[w] &= ~mask;
    }
}
