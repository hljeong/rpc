from pack import pack
from py_utils.context import Resource
import sock


class Client(Resource):
    def __init__(self, port=3727):
        super().__init__()
        self.client = None
        self.port = port

    def acquire(self):
        # todo: [0] these are supposed to be typecheck-only asserts, make them so
        assert self.client is None
        self.client = sock.Client(port=self.port)
        self.client.open()
        return self

    def release(self):
        # todo: see [0]
        assert self.client is not None
        self.client.close()
        self.client = None

    def stop_server(self):
        # todo: see [0]
        assert self.client is not None
        self.client.stop_server()

    def __getattr__(self, handle):
        def call(*args):
            # todo: see [0]
            assert self.client is not None

            # request type = 1: signature request
            self.client.send(
                (pack.pack_one(1, T=pack.uint8_type) + pack.pack_one(handle)).data
            )

            # signature request response format: {handle_exists[, return_type_info, arity, arg_type_info...]}
            # todo: error handling
            # todo: easier way to define protocols
            up = pack.Unpacker(self.client.receive())

            handle_exists = up.unpack(pack.bool_type)
            if handle_exists is None:
                raise RuntimeError("could not unpack signature request response")

            if not handle_exists:
                raise ValueError(f"unknown function handle: {handle}")

            return_type_info = up.unpack(pack.type_info_type)
            if return_type_info is None:
                raise RuntimeError("could not unpack signature")

            arity = up.unpack(pack.uint8_type)
            if arity is None:
                raise RuntimeError("could not unpack signature")

            if len(args) != arity:
                raise ValueError(
                    f"wrong number of arguments: {args} ({len(args)}), expected {arity}"
                )

            arg_type_infos = list()
            for _ in range(arity):
                arg_type_info = up.unpack(pack.type_info_type)
                if arg_type_info is None:
                    raise RuntimeError("could not unpack signature")
                arg_type_infos.append(arg_type_info)

            packed_args = pack.pack(
                *(
                    pack.typed(arg, T=arg_type_info.T)
                    for arg, arg_type_info in zip(args, arg_type_infos)
                )
            )

            # request type = 0: call
            self.client.send(
                (
                    pack.pack_one(0, T=pack.uint8_type)
                    + pack.pack(handle)
                    + packed_args
                ).data
            )

            # call response format: {handle_exists[, optional return_value]}
            up = pack.Unpacker(self.client.receive())

            # todo: change this to a uint8 status instead
            handle_exists = up.unpack(pack.bool_type)
            if handle_exists is None:
                raise RuntimeError("could not unpack signature request response")

            if not handle_exists:
                raise ValueError(f"unknown function handle: {handle}")

            res = up.unpack(pack.optional_type.of(return_type_info.T))
            if res is None:
                raise RuntimeError("could not unpack result")

            # todo: better diagnostic with better return status
            if res is pack.Nullopt:
                raise RuntimeError("call did not return a value")

            return res

        return call
