include makefile_utils/defaults.mk

CC = g++ -Wall -g -std=c++17
PYTHON = python3

.PHONY: all clean test update cpp

test: cpp
	@ # elaborate scheme to:
	@ # - run c++ server in background,
	@ # - run pytest,
	@ # - wait for c++ server to terminate, and
	@ # - verify both exited with 0
	@ \
	./a.out & . ./$(VENV_ACTIVATE) && python -m pytest -v --ignore=lib -s; \
	P=$$?; \
	wait $$!; \
	(exit $$?) && (exit $$P) && true || false
	@ echo "all tests passed"

clean: python-clean
	@ rm -rf a.out

update: git-submodule-update venv-force-install-deps

setup: git-hook-install venv-setup

cpp: cpp/rpc.h cpp/test.cc
	@ $(CC) cpp/test.cc

include makefile_utils/git.mk
include makefile_utils/python.mk
include makefile_utils/venv.mk
