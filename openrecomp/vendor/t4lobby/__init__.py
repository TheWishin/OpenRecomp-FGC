"""Tekken 4 lobby client, vendored for OpenRecomp-FGC's T4 Online section.

Client-side modules only, copied unchanged from the Tekken 4 port's lobby/t4lobby, which is
T5DR Online's open-source lobby (MIT, see LICENSE) with the package renamed and the game
identity set to Tekken 4. No server, relay node, admin tool, certificate, fingerprint or
server list is included. Everything is standard-library Python.

    t4lobby.proto      wire format shared by client and server
    t4lobby.client     LobbyClient -- what the launcher uses
    t4lobby.handover   MatchTicket (role, ports, peer, key, seed)
    t4lobby.t4game     MatchTicket -> the T4 game's TEKKEN4_NET* environment
    t4lobby.buildid    the build identity both players must share
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
