from pytest import raises

from pack import pack
from rpc import Client, RPCError


def test_rpc():
    with Client() as rpc:
        assert rpc.add(3, 5) == 8
        assert rpc.seq(20, 10) == list(range(20, 30))
        assert rpc.no_args() == -5
        assert rpc.return_void(False) == pack.Unit

        with raises(RPCError):
            rpc.error()

        assert rpc.x == 5
        rpc.x = 6
        assert rpc.x == 6

        assert rpc.y == "const"
        with raises(RPCError):
            rpc.y = "mutable"

        rpc.stop_server()
