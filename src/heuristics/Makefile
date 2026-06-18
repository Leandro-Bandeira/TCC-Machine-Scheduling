CXX = g++
CXXFLAGS = -std=c++17

SRCS = main.cpp utils/read_instance.cpp algorithms/ils.cpp
TARGET = heuristic

$(TARGET): $(SRCS)
	$(CXX) $(CXXFLAGS) $(SRCS) -o $(TARGET)

clean:
	rm -f $(TARGET)
