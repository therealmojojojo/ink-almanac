# Convenience targets for the host simulator.
BUILD ?= build
GEN ?= Unix Makefiles

.PHONY: configure build sim power-budget clean

configure:
	cmake -G "$(GEN)" -B $(BUILD) -S .

build: configure
	cmake --build $(BUILD) -j

sim: build
	./$(BUILD)/firmware_sim

power-budget: build
	./$(BUILD)/firmware_sim --test-case="power-budget*"

clean:
	rm -rf $(BUILD)
