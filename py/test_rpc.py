from pack import pack
from rpc import Client


def test_rpc():
    with Client() as (rpc, c):
        assert rpc.add(3, 5) == 8
        assert rpc.seq(20, 10) == list(range(20, 30))
        assert rpc.no_args() == -5
        assert rpc.return_void(False) == pack.Unit

        c.stop_server()
