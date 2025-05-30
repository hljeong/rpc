from enum import Enum

from pack import pack
from py_utils.context import Resource
import sock

# todo: error handling on all unpacks


# todo: these should probably be moved to some rpc.py
class RequestType(Enum):
    Call = 0
    Signature = 1
    Handles = 2
    Vars = 3


class StatusCode(Enum):
    Ok = 0
    Error = 1
    InvalidRequest = 2
    UnknownHandle = 3
    ExecutionError = 4


class RPCError(Exception):
    def __init__(self, info):
        if isinstance(info, StatusCode):
            super().__init__(f"server response: {info.name.replace('_', ' ').lower()}")

        else:
            super().__init__(info)


class Ref:
    def __init__(self, name, getter, setter):
        self.name = name
        self.getter = getter
        self.setter = setter

    def __repr__(self):
        return f"Ref[{self.name}]"

    def __get__(self, *_):
        if self.getter is None:
            raise RPCError(f"invalid access: {self.name} is not readable")
        return self.getter()

    def __set__(self, _, value):
        if self.setter is None:
            raise RPCError(f"invalid access: {self.name} is not writable")
        return self.setter(value)


class Client(Resource):
    def __init__(self, port=3727):
        super().__init__()
        self.client = None
        self.port = port
        self.funcs = dict()
        self.vars = dict()

    def acquire(self):
        # todo: [0] these are supposed to be typecheck-only asserts, make them so
        assert self.client is None
        self.client = sock.TCPClient(port=self.port)
        self.client.open()

        self.client.send(pack.pack_one[pack.UInt8](RequestType.Handles.value).data)

        # handle list request response format: [handle, ...]
        handles = pack.unpack_one[pack.List[pack.String]](self.client.receive())
        if handles is None:
            raise RuntimeError("could not unpack handle list request response")

        for handle in handles:
            self._register(handle)

        self.client.send(pack.pack_one[pack.UInt8](RequestType.Vars.value).data)

        # handle list request response format: [(name, getter_handle, setter_handle), ...]
        vars = pack.unpack_one[
            pack.List[
                pack.Tuple[
                    pack.String, pack.Optional[pack.String], pack.Optional[pack.String]
                ]
            ]
        ](self.client.receive())
        if handles is None:
            raise RuntimeError("could not unpack var list request response")

        for name, getter_handle, setter_handle in vars:
            self._register_var(name, getter_handle, setter_handle)

        class Remote:
            def __init__(self, funcs):
                for handle, func in funcs.items():
                    setattr(self, handle, func)

            def __repr__(self):
                return "<RPC Remote>"

        for name, var in self.vars.items():
            setattr(Remote, name, var)

        remote = Remote(self.funcs)

        return remote

    def release(self):
        # todo: see [0]
        assert self.client is not None
        self.vars = dict()
        self.funcs = dict()
        self.client.close()
        self.client = None

    # todo: clean up logic for registry... so ugly
    def _register(self, handle):
        # todo: see [0]
        assert self.client is not None

        self.client.send(
            (
                pack.pack_one[pack.UInt8](RequestType.Signature.value)
                + pack.pack_one(handle)
            ).data
        )

        # signature request response format: {status[, return_type_info, arity, arg_type_info...]}
        # todo: error handling
        # todo: easier way to define protocols
        up = pack.Unpacker(self.client.receive())

        status = up.unpack[pack.UInt8]()
        status = StatusCode(status)
        if status != StatusCode.Ok:
            if status == StatusCode.UnknownHandle:
                raise RPCError(f"unknown function handle: {handle}")
            else:
                raise RPCError(status)

        return_type_info = up.unpack[pack.TypeInfoType]()
        arity = up.unpack[pack.UInt8]()
        arg_type_infos = list()
        for _ in range(arity):
            arg_type_info = up.unpack[pack.TypeInfoType]()
            arg_type_infos.append(arg_type_info)

        def call(*args):
            # todo: see [0]
            assert self.client is not None

            if len(args) != arity:
                raise ValueError(
                    f"wrong number of arguments for '{handle}': got {len(args)} ({', '.join(map(str, args))}), expected {arity}"
                )

            # todo: restructure this call once pack.pack supports parametrization
            packed_args = pack.pack(
                *(
                    arg_type_info.T(arg)
                    for arg, arg_type_info in zip(args, arg_type_infos)
                )
            )

            self.client.send(
                (
                    pack.pack_one[pack.UInt8](RequestType.Call.value)
                    + pack.pack(handle)
                    + packed_args
                ).data
            )

            # call response format: {status[, return_value]}
            up = pack.Unpacker(self.client.receive())

            status = up.unpack[pack.UInt8]()
            status = StatusCode(status)
            if status != StatusCode.Ok:
                if status == StatusCode.UnknownHandle:
                    raise RPCError(f"unknown function handle: {handle}")
                elif status == StatusCode.ExecutionError:
                    raise RPCError(
                        f"execution error during call to {handle}({', '.join(map(repr, args))}): {up.unpack[pack.String]()}"
                    )
                else:
                    raise RPCError(status)

            return up.unpack[return_type_info.T]()

        self.funcs[handle] = call

    def _register_var(self, name, getter_handle, setter_handle):
        # todo: see [0]
        assert self.client is not None

        self.vars[name] = Ref(
            name, self.funcs.get(getter_handle), self.funcs.get(setter_handle)
        )
