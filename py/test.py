from client import Client, pack


def main():
    c = Client()
    assert c.add(3, 5) == 8
    assert c.seq(20, 10) == list(range(20, 30))
    assert c.no_args() == -5
    assert c.return_void(False) == pack.Unit()
    c.close()


if __name__ == "__main__":
    main()
