#pragma once

#include <map>
#include <tuple>

#include "../lib/pack/cpp/pack.h"
#include "../lib/sock/cpp/sock.h"

namespace rpc {

template <typename> struct func_traits;

template <typename F>
struct func_traits : func_traits<decltype(&F::operator())> {};

template <typename T, typename R, typename... As>
struct func_traits<R (T::*)(As...)> : func_traits<R (*)(As...)> {};

template <typename T, typename R, typename... As>
struct func_traits<R (T::*)(As...) const> : func_traits<R (*)(As...)> {};

template <typename R, typename... As> struct func_traits<R (*)(As...)> {
  using return_type = R;

  static const std::size_t arity = sizeof...(As);

  using arg_types = std::tuple<As...>;

  template <std::size_t I>
  using arg_type =
      typename std::tuple_element_t<I,
                                    std::tuple<typename std::decay_t<As>...>>;
};

template <typename F> using return_type = typename func_traits<F>::return_type;

template <typename F, std::size_t I>
using nth_arg_type = typename func_traits<F>::template arg_type<I>;

template <typename F> constexpr std::size_t arity = func_traits<F>::arity;

template <typename F>
constexpr bool returns_void = std::is_same_v<return_type<F>, void>;

template <typename F, typename T>
auto packable_apply(F f, T t)
    -> std::conditional_t<returns_void<F>, pack::Unit, return_type<F>> {
  if constexpr (returns_void<F>) {
    std::apply(f, t);
    return pack::Unit();
  } else {
    return std::apply(f, t);
  };
};

template <typename F, std::size_t... Is>
auto invoke(F f, pack::Pack pack, std::index_sequence<Is...>) {
  const auto args_opt = pack::unpack<nth_arg_type<F, Is>...>(pack);
  return args_opt ? std::make_optional(packable_apply(f, *args_opt))
                  : std::nullopt;
}

template <typename F> decltype(auto) invoke(F f, pack::Pack pack) {
  return invoke(f, pack, std::make_index_sequence<arity<F>>());
}

// signature: {return_type_info, arity, arg_type_info...}
// todo: make custom packable type?
template <typename F, std::size_t... Is>
pack::Pack signature(F f, pack::TypeInfo return_type_info,
                     std::index_sequence<Is...>) {
  pack::Packer p;
  p.pack(return_type_info);
  p.pack<uint8_t>(arity<F>);
  (p.pack(pack::type_info<nth_arg_type<F, Is>>), ...);
  return *p;
}

template <typename F, std::enable_if_t<!returns_void<F>, bool> = true>
static pack::Pack signature(F f) {
  return signature(f, pack::type_info<return_type<F>>,
                   std::make_index_sequence<arity<F>>());
}

template <typename F, std::enable_if_t<returns_void<F>, bool> = true>
static pack::Pack signature(F f) {
  return signature(f, pack::type_info<pack::Unit>,
                   std::make_index_sequence<arity<F>>());
}

class UniversalFunc {
public:
  UniversalFunc() : UniversalFunc([]() {}) {}

  template <typename F>
  UniversalFunc(F f)
      : m_func([=](const pack::Pack &pack) {
          return pack::pack_one(invoke(f, pack));
        }),
        m_signature(signature(f)) {}

  pack::Pack operator()(const pack::Pack &pack) const { return m_func(pack); }

  pack::Pack get_signature() const { return m_signature; }

private:
  std::function<pack::Pack(const pack::Pack &)> m_func;
  pack::Pack m_signature;
};

class Server : public sock::Server {
public:
  Server(uint16_t port = 3727)
      : sock::Server([this](auto data, auto len) { callback(data, len); },
                     port) {}

  virtual ~Server() = default;

  template <typename F> void bind(std::string handle, F f) {
    m_funcs[handle] = UniversalFunc(f);
  }

private:
  void callback(const uint8_t *data, uint32_t len) {
    pack::Unpacker up(pack::Bytes(data, data + len));

    const auto request_opt = up.unpack<uint8_t>();
    if (!request_opt) {
      // failed to unpack request id
      return;
    }

    const auto request = *request_opt;
    if (request == 0) {
      // call
      const auto handle_opt = up.unpack<std::string>();
      if (!handle_opt) {
        // failed to unpack function handle
        // todo: update protocol to use more descriptive status
        send(pack::pack(false));
        return;
      }

      const auto handle = *handle_opt;
      if (!m_funcs.count(handle)) {
        // unknown function handle
        // todo: update protocol to use more descriptive status
        send(pack::pack(false));
        return;
      }

      send(pack::Pack(pack::pack(true), m_funcs[handle](up.consume())));
    } else if (request == 1) {
      // signature request
      const auto handle_opt = up.unpack<std::string>();
      if (!handle_opt) {
        // failed to unpack function handle
        // todo: update protocol to use more descriptive status
        send(pack::pack(false));
      }

      const auto handle = *handle_opt;
      if (!m_funcs.count(handle)) {
        // unknown function handle
        // todo: update protocol to use more descriptive status
        send(pack::pack(false));
        return;
      }

      send(pack::Pack(pack::pack(true), m_funcs[handle].get_signature()));
    } else {
      // unknown request type
      send(pack::pack(false));
      return;
    }
  }

  std::map<std::string, UniversalFunc> m_funcs;
};

}; // namespace rpc