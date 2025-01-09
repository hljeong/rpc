# todo: python version, venv?
CC = g++ -Wall -g -std=c++17
PY = python3

.PHONY: all clean test cpp

all: test

clean:
	rm -rf a.out

test: cpp py
	@./a.out &
	@$(PY) py/test.py
	@wait $!
	@echo "all tests passed"

cpp: cpp/server.h cpp/test.cc
	@$(CC) cpp/test.cc

py: py/client.py py/test.py
