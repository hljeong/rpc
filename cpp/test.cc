#include <cassert>

#include "server.h"

using namespace rpc;

uint32_t add(uint32_t x, uint32_t y) { return x + y; }

std::vector<uint64_t> seq(uint64_t start, uint16_t len) {
  std::vector<uint64_t> s;
  for (uint16_t i = 0; i < len; ++i) {
    s.push_back(start + i);
  }
  return s;
}

int8_t no_args() { return -5; }

void return_void(bool) {}

int main() {
  rpc::Server s;
  s.bind("add", add);
  s.bind("seq", seq);
  s.bind("no_args", no_args);
  s.bind("return_void", return_void);
  s.start();
  std::this_thread::sleep_for(std::chrono::seconds(1));
  s.stop();
}
