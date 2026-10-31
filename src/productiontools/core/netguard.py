"""App-level outbound network lock.

IMPORTANT - what this is and is not
-----------------------------------
This is an *application-level safeguard*. Once installed, any attempt by
ProductionTools' own Python code (or a library it loads) to open a network
connection to anything other than this computer (loopback / 127.0.0.1) is
refused and recorded.

It is NOT operating-system enforcement:
  * it cannot see or stop other programs (e.g. Excel, a browser, LibreOffice),
  * native code that bypasses Python's socket module would not be caught.

Independent, OS-level outbound protection requires an outbound firewall such
as LuLu or Little Snitch, or simply turning networking off. (macOS's built-in
firewall only filters *incoming* connections and does not stop outbound data.)
"""

from __future__ import annotations

import ipaddress
import socket
import threading
import time
from dataclasses import dataclass, field

_LOCK = threading.Lock()
_INSTALLED = False
_ORIGINALS: dict[str, object] = {}


class NetworkBlockedError(ConnectionRefusedError):
    """Raised when code tries to reach a non-local network address."""


@dataclass
class Attempt:
    when: float
    target: str
    via: str


@dataclass
class _Log:
    attempts: list[Attempt] = field(default_factory=list)


LOG = _Log()


def _is_local(host) -> bool:
    if host is None:
        return False
    if isinstance(host, bytes):
        host = host.decode("utf-8", "replace")
    host = str(host).strip("[]")
    if host in ("localhost", ""):
        return host == "localhost"
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return False  # a hostname that is not "localhost" would need DNS -> not local


def _check(address, via: str):
    # AF_UNIX sockets use a filesystem path (str/bytes) -> always local.
    if isinstance(address, (str, bytes)):
        return
    host = address[0] if isinstance(address, tuple) and address else address
    if not _is_local(host):
        LOG.attempts.append(Attempt(time.time(), repr(address), via))
        raise NetworkBlockedError(
            f"ProductionTools network lock: outbound connection to {address!r} blocked"
        )


def install() -> None:
    """Install the lock for this Python process (idempotent)."""
    global _INSTALLED
    with _LOCK:
        if _INSTALLED:
            return
        _ORIGINALS["connect"] = socket.socket.connect
        _ORIGINALS["connect_ex"] = socket.socket.connect_ex
        _ORIGINALS["sendto"] = socket.socket.sendto
        _ORIGINALS["getaddrinfo"] = socket.getaddrinfo

        orig_connect = socket.socket.connect
        orig_connect_ex = socket.socket.connect_ex
        orig_sendto = socket.socket.sendto
        orig_getaddrinfo = socket.getaddrinfo

        def connect(self, address):
            _check(address, "socket.connect")
            return orig_connect(self, address)

        def connect_ex(self, address):
            _check(address, "socket.connect_ex")
            return orig_connect_ex(self, address)

        def sendto(self, data, *args):
            address = args[-1]
            _check(address, "socket.sendto")
            return orig_sendto(self, data, *args)

        def getaddrinfo(host, *args, **kwargs):
            # Refuse DNS lookups of outside names: a DNS query itself leaks data.
            if host is not None and not _is_local(host):
                LOG.attempts.append(Attempt(time.time(), repr(host), "getaddrinfo"))
                raise NetworkBlockedError(
                    f"ProductionTools network lock: DNS lookup of {host!r} blocked"
                )
            return orig_getaddrinfo(host, *args, **kwargs)

        socket.socket.connect = connect
        socket.socket.connect_ex = connect_ex
        socket.socket.sendto = sendto
        socket.getaddrinfo = getaddrinfo
        _INSTALLED = True


def uninstall() -> None:
    """Remove the lock (used only by tests)."""
    global _INSTALLED
    with _LOCK:
        if not _INSTALLED:
            return
        socket.socket.connect = _ORIGINALS["connect"]
        socket.socket.connect_ex = _ORIGINALS["connect_ex"]
        socket.socket.sendto = _ORIGINALS["sendto"]
        socket.getaddrinfo = _ORIGINALS["getaddrinfo"]
        _INSTALLED = False


def is_installed() -> bool:
    return _INSTALLED


def summary() -> dict:
    return {
        "lock_installed": _INSTALLED,
        "outbound_attempts_blocked": len(LOG.attempts),
        "attempts": [a.__dict__ for a in LOG.attempts],
        "scope": "application-level (this Python process only); not OS-enforced",
    }
