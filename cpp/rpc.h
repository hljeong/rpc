#ifndef RPC_H
#define RPC_H

#include <map>
#include <optional>
#include <tuple>
#include <type_traits>

#include "../lib/pack/cpp/pack.h"
#include "../lib/sock/cpp/sock.h"

namespace rpc {

// todo: move func_traits out?
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
  return packable_apply(f, pack::unpack<nth_arg_type<F, Is>...>(pack));
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

using Handle = std::string;
using Name = std::string;

enum RequestType : uint8_t {
  Call = 0,
  SignatureRequest = 1,
  HandleListRequest = 2,
  VarListRequest = 3,
};

enum StatusCode : uint8_t {
  Ok = 0,
  Error = 1,
  InvalidRequest = 2,
  UnknownHandle = 3,
  ExecutionError = 4,
};

enum class Access : uint8_t {
  None = 0,
  Read = 1,
  Write = 2,
  ReadWrite = 3,
};

inline bool operator&(Access lhs, Access rhs) {
  using T = std::underlying_type_t<Access>;
  return static_cast<bool>(static_cast<T>(lhs) & static_cast<T>(rhs));
}

template <typename T>
std::function<std::remove_const_t<T>()> make_getter(T &var) {
  return [&]() { return var; };
}

template <typename T, std::enable_if_t<!std::is_const_v<T>, bool> = true>
std::function<void(T &)> make_setter(T &var) {
  return [&](const T &value) { var = value; };
}

class Server : public sock::TCPCallbackServer {
public:
  Server(uint16_t port = 3727)
      : sock::TCPCallbackServer(
            port, [this](auto data, auto len) { callback(data, len); }) {}

  virtual ~Server() noexcept = default;

  Server(Server &&other) noexcept
      : sock::TCPCallbackServer(std::move(other), [&](auto data, auto len) {
          callback(data, len);
        }) {}

  Server &operator=(Server &&) noexcept = default;

  template <typename F> void bind(const Handle &handle, F f) {
    // todo: log overwrite
    m_funcs[handle] = UniversalFunc(f);
  }

  // todo: unify bind() syntax
  template <typename T>
  void bind_var(const Name &name, T &var, Access access = Access::ReadWrite) {
    std::optional<Handle> getter_handle = std::nullopt;
    std::optional<Handle> setter_handle = std::nullopt;

    if (access & Access::Read) {
      getter_handle = "get_" + name;
      bind(*getter_handle, make_getter(var));
    }

    if (access & Access::Write) {
      setter_handle = "set_" + name;
      bind(*setter_handle, make_setter(var));
    }

    m_vars[name] = {getter_handle, setter_handle};
  }

  template <typename T>
  void bind_var(const Name &name, const T &var, Access access = Access::Read) {
    std::optional<Handle> getter_handle = std::nullopt;

    if (access & Access::Read) {
      getter_handle = "get_" + name;
      bind(*getter_handle, make_getter(var));
    }

    if (access & Access::Write) {
      // todo: log invalid access
    }

    m_vars[name] = {getter_handle, std::nullopt};
  }

private:
  void callback(const uint8_t *data, uint32_t len) {
    pack::Unpacker up(pack::Bytes(data, data + len));

    try {
      const auto request_type = up.unpack<uint8_t>();
      switch (request_type) {
      case Call: {
        const auto handle = up.unpack<Handle>();
        if (!m_funcs.count(handle)) {
          send(pack::pack(UnknownHandle));
          return;
        }

        try {
          const auto return_value = m_funcs[handle](up.consume());
          send(pack::Pack(pack::pack(Ok), return_value));
        } catch (const std::runtime_error &e) {
          send(pack::Pack(pack::pack(ExecutionError),
                          pack::pack(std::string_view(e.what()))));
        }
        break;
      }

      case SignatureRequest: {
        const auto handle = up.unpack<Handle>();
        if (!m_funcs.count(handle)) {
          send(pack::pack(UnknownHandle));
          return;
        }

        send(pack::Pack(pack::pack(Ok), m_funcs[handle].get_signature()));
        break;
      }

      case HandleListRequest: {
        std::vector<Handle> handles;
        for (const auto &[handle, _] : m_funcs) {
          handles.push_back(handle);
        }

        send(pack::pack(handles));
        break;
      }

      case VarListRequest: {
        std::vector<
            std::tuple<Name, std::optional<Handle>, std::optional<Handle>>>
            vars;
        for (const auto &[name, accessors] : m_vars) {
          const auto &[getter, setter] = accessors;
          vars.push_back({name, getter, setter});
        }

        send(pack::pack(vars));
        break;
      }

      default: {
        send(pack::pack(InvalidRequest));
        break;
      }
      };
    } catch (const std::runtime_error &e) {
      // todo: more granularity on this try catch
      send(pack::pack(Error));
    }
  }

  std::map<Handle, UniversalFunc> m_funcs;
  std::map<Name, std::tuple<std::optional<Handle>, std::optional<Handle>>>
      m_vars;
};

} // namespace rpc

#endif
