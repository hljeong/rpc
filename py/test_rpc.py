from pytest import raises

from pack import pack
from rpc import Client, RPCError
from rpc.client import Ref


def test_rpc():
    with Client() as (rpc, c):
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

        c.stop_server()
