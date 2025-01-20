#include <cassert>

#include "../lib/cpp_utils/srv/srv.h"
#include "rpc.h"

using namespace rpc;
using namespace sock;
using namespace srv;
using namespace std;

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

std::tuple<uint32_t, std::string, std::optional<bool>, std::vector<int8_t>>
test_tuple(
    std::tuple<std::vector<int8_t>, std::optional<bool>, std::string, uint32_t>
        x) {
  return {std::get<3>(x), std::get<2>(x), std::get<1>(x), std::get<0>(x)};
}

bool error() { throw std::runtime_error("calling error();"); }

int x = 5;

const std::string y = "const";

int main() {
  using namespace std::chrono;
  using namespace std::this_thread;

  AutoDispatch s(make_unique<Server>(), 5s);

  s->bind("add", add);
  s->bind("seq", seq);
  s->bind("no_args", no_args);
  s->bind("return_void", return_void);
  s->bind("test_tuple", test_tuple);
  s->bind("error", error);
  s->bind_var("x", x);
  try {
    s->bind_var("y", y);
  } catch (const std::exception &e) {
    printf("%s\n", e.what());
  }
  s->bind("stop_server", [&] { s.signal_stop(); });

  s.join();
}
