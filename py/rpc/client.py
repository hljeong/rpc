from enum import Enum

from pack import pack
from py_utils.context import Resource
import sock

# todo: error handling on all unpacks


# todo: these should probably be moved to some rpc.py
class RequestType(Enum):
    CALL = 0
    SIGNATURE_REQUEST = 1
    HANDLE_LIST_REQUEST = 2


class StatusCode(Enum):
    OK = 0
    ERROR = 1
    INVALID_REQUEST = 2
    UNKNOWN_HANDLE = 3
    EXECUTION_ERROR = 4


class RPCError(Exception):
    def __init__(self, info):
        if isinstance(info, StatusCode):
            super().__init__(f"server response: {info.name.replace('_', ' ').lower()}")

        else:
            super().__init__(info)


class Client(Resource):
    class Remote:
        def __init__(self, funcs):
            for handle, func in funcs.items():
                setattr(self, handle, func)

    def __init__(self, port=3727):
        super().__init__()
        self.client = None
        self.port = port
        self.funcs = dict()

    def acquire(self):
        # todo: [0] these are supposed to be typecheck-only asserts, make them so
        assert self.client is None
        self.client = sock.Client(port=self.port)
        self.client.open()

        self.client.send(
            pack.pack_one[pack.UInt8](RequestType.HANDLE_LIST_REQUEST.value).data
        )

        # handle list request response format: [handle, ...]
        handles = pack.unpack_one[pack.List[pack.String]](self.client.receive())
        if handles is None:
            raise RuntimeError("could not unpack handle list request response")

        for handle in handles:
            self._register(handle)
        remote = Client.Remote(self.funcs)

        return remote, self

    def release(self):
        # todo: see [0]
        assert self.client is not None
        self.funcs = dict()
        self.client.close()
        self.client = None

    def stop_server(self):
        # todo: see [0]
        assert self.client is not None
        self.client.stop_server()

    def _register(self, handle):
        # todo: see [0]
        assert self.client is not None

        self.client.send(
            (
                pack.pack_one[pack.UInt8](RequestType.SIGNATURE_REQUEST.value)
                + pack.pack_one(handle)
            ).data
        )

        # signature request response format: {status[, return_type_info, arity, arg_type_info...]}
        # todo: error handling
        # todo: easier way to define protocols
        up = pack.Unpacker(self.client.receive())

        status = up.unpack[pack.UInt8]()
        status = StatusCode(status)
        if status != StatusCode.OK:
            if status == StatusCode.UNKNOWN_HANDLE:
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
                    pack.pack_one[pack.UInt8](RequestType.CALL.value)
                    + pack.pack(handle)
                    + packed_args
                ).data
            )

            # call response format: {status[, return_value]}
            up = pack.Unpacker(self.client.receive())

            status = up.unpack[pack.UInt8]()
            status = StatusCode(status)
            if status != StatusCode.OK:
                if status == StatusCode.UNKNOWN_HANDLE:
                    raise RPCError(f"unknown function handle: {handle}")
                elif status == StatusCode.EXECUTION_ERROR:
                    raise RPCError(
                        f"execution error during call to {handle}({', '.join(map(repr, args))}): {up.unpack[pack.String]()}"
                    )
                else:
                    raise RPCError(status)

            return up.unpack[return_type_info.T]()

        self.funcs[handle] = call
