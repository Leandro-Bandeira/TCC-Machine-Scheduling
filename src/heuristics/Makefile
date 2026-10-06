CXX = g++
CXXFLAGS = -std=c++17 -O3 -march=native

SRCS = main.cpp utils/read_instance.cpp utils/objective.cpp utils/utils.cpp algorithms/ils.cpp algorithms/LocalSearch.cpp
HDRS = $(shell find . -name "*.hpp")
TARGET = heuristic

$(TARGET): $(SRCS) $(HDRS)
	$(CXX) $(CXXFLAGS) $(SRCS) -o $(TARGET)

clean:
	rm -f $(TARGET)
.PHONY: clean
