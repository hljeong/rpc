from pack import pack
from rpc import Client


def test_rpc():
    with Client() as c:
        assert c.add(3, 5) == 8
        assert c.seq(20, 10) == list(range(20, 30))
        assert c.no_args() == -5
        assert c.return_void(False) == pack.Unit

        c.stop_server()
