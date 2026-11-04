"""T5DR Online lobby: matchmaking service and client library.

Everything here is standard-library Python (3.10+), so the launcher and a
self-hosted server need nothing installed. See docs/ONLINE.md.

    t4lobby.proto      wire format shared by client and server
    t4lobby.client     LobbyClient -- what the launcher uses
    t4lobby.handover   MatchTicket -> environment for t5dr.exe (netplay)
    t4lobby.buildid    the build identity both players must share
    t4lobby.rating     Glicko-2
    t4lobby.server     the lobby server (python -m t4lobby.server)
"""
__version__ = "0.1.0"

from .proto import PROTO_VERSION, DEFAULT_PORT, LobbyError  # noqa: F401
from .buildid import BuildInfo  # noqa: F401


def __getattr__(name):
    # Lazy: importing the package for the server must not pull in client code and vice versa.
    if name == "LobbyClient":
        from .client import LobbyClient
        return LobbyClient
    if name == "MatchTicket":
        from .handover import MatchTicket
        return MatchTicket
    raise AttributeError(name)
