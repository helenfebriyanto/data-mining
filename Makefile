.DEFAULT_GOAL := help

.PHONY: help run-phase-1 run-phase-2 run-phase-3 run-phase-4 run-phase-5 clean

help:
	@echo "Available targets:"
	@echo "  make help          Show this help"
	@echo "  make run-phase-1   Run phase 1"
	@echo "  make run-phase-2   Run phase 2"
	@echo "  make run-phase-3   Run phase 3"
	@echo "  make run-phase-4   Run phase 4"
	@echo "  make run-phase-5   Run phase 5"
	@echo "  make clean         Remove temporary outputs (reports/tmp)"

run-phase-1:
	python phase_1/phase_1.py

run-phase-2:
	python phase_2/phase_2.py

run-phase-3:
	python phase_3/phase_3.py

run-phase-4:
	python phase_4/phase_4.py

run-phase-5:
	python phase_5/app.py

clean:
	rm -rf reports/tmp
