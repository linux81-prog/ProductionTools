import socket
import threading

import pytest

from productiontools.core import netguard


def test_outbound_connection_is_blocked_and_recorded():
    before = len(netguard.LOG.attempts)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(netguard.NetworkBlockedError):
        s.connect(("203.0.113.10", 443))  # TEST-NET-3 documentation address; never actually contacted
    s.close()
    assert len(netguard.LOG.attempts) == before + 1


def test_dns_lookup_of_outside_name_is_blocked():
    with pytest.raises(netguard.NetworkBlockedError):
        socket.getaddrinfo("example.com", 443)


def test_udp_send_to_outside_is_blocked():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    with pytest.raises(netguard.NetworkBlockedError):
        s.sendto(b"x", ("198.51.100.7", 53))
    s.close()


def test_loopback_is_allowed():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    t = threading.Thread(target=lambda: srv.accept()[0].close())
    t.start()
    c = socket.socket()
    c.connect(("127.0.0.1", port))
    c.close()
    t.join(5)
    srv.close()


def test_summary_states_scope_honestly():
    s = netguard.summary()
    assert s["lock_installed"] is True
    assert "not OS-enforced" in s["scope"]
