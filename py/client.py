import importlib.util
import pathlib


# todo: move this to py_utils
def import_from_path(path):
    name = pathlib.Path(path).stem

    spec = importlib.util.spec_from_file_location(name, path)

    assert spec is not None
    mod = importlib.util.module_from_spec(spec)

    assert spec.loader is not None
    spec.loader.exec_module(mod)

    return mod


pack = import_from_path(pathlib.Path(__file__).parent / "../lib/pack/py/pack.py")
# todo: rename client.py to sock.py
sock = import_from_path(pathlib.Path(__file__).parent / "../lib/sock/py/client.py")


class Client:
    def __init__(self, port=3727):
        self.client = sock.Client(port=port)

        if not self.client.open():
            raise RuntimeError("could not open socket")

        if not self.client.connect():
            self.close()
            raise RuntimeError("could not connect")

    def close(self):
        self.client.close()

    def __getattr__(self, handle):
        def call(*args):
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
            if res is pack.optional_type.NULLOPT:
                raise RuntimeError("call did not return a value")

            return res

        return call
