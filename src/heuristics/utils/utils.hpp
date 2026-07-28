#pragma once
#include "../models/solution.hpp"
#include <cstdint>
#include <vector>

void printRoutes(const Solution& solution);
void set_range(std::vector<uint64_t>& bits, int start, int end);
void unset_range(std::vector<uint64_t>& bits, int start, int end);
