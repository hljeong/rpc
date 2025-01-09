# todo: python version, venv?
CC = g++ -Wall -g -std=c++17
PY = python3

.PHONY: all clean test update cpp py

all: test

clean:
	rm -rf a.out

test: cpp py
	@./a.out &
	@$(PY) py/test.py
	@wait $!
	@echo "all tests passed"

update:
	@git submodule foreach git pull origin main

cpp: cpp/server.h cpp/test.cc
	@$(CC) cpp/test.cc

py: py/client.py py/test.py
