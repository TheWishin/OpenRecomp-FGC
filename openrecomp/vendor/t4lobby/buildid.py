"""The build identity both players of a Tekken 4 match must share.

Tekken 4 copy of T5DR Online's lobby/t5lobby/buildid.py (docs/LOBBY.md). Rollback netplay only works when both PCs
run identical game code. That code is fixed by three things (tools/t4_buildid.py computes them at build time and
writes <exe dir>/t4net_build.txt = "<id> <elf_sha1> <code_id> <net>"):

    elf_sha1  SHA-1 of game/disc/SLUS_203.28 (SLUS-20328 v1.00: a4b7dde2...)
    code_id   SHA-1 over the PS2Recomp tree (commit + uncommitted diff), patches/*.patch, config/*.toml|*.csv and the
              game modules staged into the runner (*_overrides.cpp, tekken4_net*) -- tools/t4_buildid.py code_id()
    net       the netplay wire version (runtime/tekken4_net.h kNetVersion)

build id = first 16 hex digits of SHA-1("t4dr-build:<elf_sha1>:<code_id>:<net>")   (T5DR: "t5dr-build:..."),
the same value the game puts into its HELLO (TEKKEN4_NET_BUILD). The prefix alone already keeps a T4 id from ever
equalling a T5DR id; the "game" field ("t4") is checked by the server as well. The release string is informational.
"""
import hashlib
import json
import os
from dataclasses import dataclass, field

from .proto import GAME

PREFIX = "t4dr-build"
NETPLAY_VERSION = 1    # runtime/tekken4_net.h kNetVersion ("T4NP" v1); raise together with it
STAMP = "t4net_build.txt"


def sha1_file(path, chunk=1 << 20):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def build_id(elf_sha1, code_id, net):
    return hashlib.sha1(f"{PREFIX}:{elf_sha1.lower()}:{code_id.lower()}:{net}".encode()).hexdigest()[:16]


@dataclass
class BuildInfo:
    elf_sha1: str
    code_id: str
    release: str = "dev"
    net: int = NETPLAY_VERSION
    build_id: str = field(default="")
    game: str = GAME

    def __post_init__(self):
        if not self.build_id:
            self.build_id = build_id(self.elf_sha1, self.code_id, self.net)

    def as_wire(self):
        return {"id": self.build_id, "elf": self.elf_sha1, "code": self.code_id,
                "net": self.net, "release": self.release, "game": self.game}

    @staticmethod
    def wire_id(build):
        """Recompute the id from a wire dict (the server does not trust the client's "id")."""
        try:
            net = int(build.get("net", 0) or 0)
        except (TypeError, ValueError):
            net = 0
        return BuildInfo(str(build.get("elf", "")), str(build.get("code", "")),
                         str(build.get("release", "")), net).build_id

    @staticmethod
    def has_online(out):
        """Every Tekken 4 netplay build (docs/rollback/net_build.cmd) has the online modules."""
        return True

    @classmethod
    def from_stamp(cls, path, release="dev", elf=None):
        """From t4net_build.txt ("<id> <elf_sha1> <code_id> <net>", tools/t4_buildid.py). With `elf` (the player's
        SLUS_203.28) its SHA-1 must be the stamp's: another disc image is another game. Raises OSError / ValueError
        when the stamp is missing or does not add up."""
        with open(path, encoding="ascii") as f:
            words = f.read().split()
        if len(words) < 4:
            raise ValueError(f"{path}: expected '<id> <elf_sha1> <code_id> <net>'")
        sid, elf_sha1, code, net = words[0], words[1], words[2], int(words[3])
        if elf is not None:
            got = sha1_file(elf)
            if got != elf_sha1.lower():
                raise ValueError(f"{elf}: SHA-1 {got}, this build was made for {elf_sha1} (SLUS-20328 v1.00)")
        info = cls(elf_sha1, code, release, net)
        if info.build_id != sid.lower():
            raise ValueError(f"{path}: id {sid} does not match its fields ({info.build_id})")
        return info

    @staticmethod
    def game_title(out):
        """The title ID of the game built in `out` (its build stamp's "title": NPUB30009 for the US release,
        NPEA00019 for the European one, 1.1.9), or None when the stamp cannot be read or has none."""
        try:
            with open(os.path.join(out, "build", "t5dr_build.json"), encoding="utf-8") as f:
                return json.load(f).get("title") or None
        except (OSError, ValueError, AttributeError):
            return None

    @classmethod
    def from_out_dir(cls, out, release="dev"):
        """From the game's exe folder (e.g. D:\\tekken4-fork-net\\out\\net\\ps2xRuntime): its t4net_build.txt."""
        return cls.from_stamp(os.path.join(out, STAMP), release)

    def stamp_json(self):
        return json.dumps(self.as_wire())
