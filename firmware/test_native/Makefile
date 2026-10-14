# Native build of the firmware core (polaris_core) with g++.
# The Vallado SGP4 sources are the same files the firmware uses.
BUILD     ?= build
SGP4_DIR  := ../lib/sgp4_vallado

CORE      := ../lib/polaris_core
CXXFLAGS  ?= -O2 -std=c++17 -Wall -Wextra -Wshadow -Wdouble-promotion -Werror
SGP4_FLAGS := -O2 -std=c++17 -w

CORE_SRC  := $(wildcard $(CORE)/*.cpp)

all: $(BUILD)/harness

$(BUILD)/sgp4.o: $(SGP4_DIR)/SGP4.cpp $(SGP4_DIR)/SGP4.h
	mkdir -p $(BUILD)
	g++ $(SGP4_FLAGS) -c $< -o $@

$(BUILD)/harness: harness.cpp axis_model.h $(CORE_SRC) $(wildcard $(CORE)/*.h) $(BUILD)/sgp4.o
	g++ $(CXXFLAGS) -I$(CORE) -isystem $(SGP4_DIR) harness.cpp $(CORE_SRC) $(BUILD)/sgp4.o -lm -o $@

clean:
	rm -rf $(BUILD)

.PHONY: all clean
