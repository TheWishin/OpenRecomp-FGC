"""The T4 lobby identity holds what Direct IP's check holds: build id fields, compiler and ISO, and the ELF on disk.

Review t4-online-b740a3a finding 1. Test files only (no game data, no server): the lobby server recomputes the id
from elf/code/net as before (BuildInfo.wire_id), so builds that differ only in compiler or ISO get different ids.
"""
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp.adapters import t4_online
from openrecomp.adapters.t4_online import T4Online
from openrecomp.vendor.t4lobby.buildid import BuildInfo

CODE = "c" * 40


class Holder:
    """Only what _t4_identity_build reads."""
    _t4_identity_build = T4Online._t4_identity_build

    def __init__(self, root, iso):
        self.root = root
        self.s = {}
        self.core = SimpleNamespace(effective_iso=lambda s: iso if os.path.isfile(iso) else "")


class LobbyIdentity(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_HOME=str(self.dir / "home")))
        self.enterContext(mock.patch.dict(t4_online._hash_cache, clear=True))
        self.api = dict(build=BuildInfo)

    def install(self, name, elf=b"elf v1", iso=b"iso image", compiler=("MSVC", "19.44.35211.0")):
        root = self.dir / name
        (root / "game" / "disc").mkdir(parents=True)
        (root / "game" / "disc" / "SLUS_203.28").write_bytes(elf)
        out = root / "bin"
        out.mkdir()
        (out / "t4net_build.json").write_text(json.dumps(dict(
            id="0" * 16, toolchain=["CXX_ID=" + compiler[0], "CXX_VERSION=" + compiler[1], "GENERATOR=Ninja"])),
            encoding="utf-8")
        (root / "game.iso").write_bytes(iso)
        import hashlib
        info = BuildInfo(hashlib.sha1(b"elf v1").hexdigest(), CODE, "0.1.0")
        return Holder(str(root), str(root / "game.iso")), info, str(out)

    def ident(self, name, **kw):
        holder, info, out = self.install(name, **kw)
        return holder._t4_identity_build(self.api, info, out)

    def test_same_inputs_same_id_and_the_server_computes_it_too(self):
        a, b = self.ident("a"), self.ident("b")
        self.assertEqual(a.build_id, b.build_id)
        self.assertEqual(BuildInfo.wire_id(a.as_wire()), a.build_id)      # the live server's rule, unchanged
        self.assertNotEqual(a.code_id, CODE)
        self.assertRegex(a.code_id, r"^[0-9a-f]{40}$")
        self.assertNotEqual(a.build_id, BuildInfo(a.elf_sha1, CODE, "0.1.0").build_id)

    def test_another_compiler_or_iso_is_another_build(self):
        base = self.ident("a").build_id
        self.assertNotEqual(self.ident("b", compiler=("MSVC", "19.43.34808.0")).build_id, base)
        self.assertNotEqual(self.ident("c", iso=b"another dump").build_id, base)

    def test_a_stale_elf_a_stamp_without_compiler_or_no_iso_is_refused(self):
        holder, info, out = self.install("a", elf=b"elf v0")
        with self.assertRaisesRegex(RuntimeError, "t4.direct_identity_failed"):
            holder._t4_identity_build(self.api, info, out)
        holder, info, out = self.install("b")
        Path(out, "t4net_build.json").write_text(json.dumps(dict(id="0" * 16, toolchain=[])), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "t4.direct_identity_failed"):
            holder._t4_identity_build(self.api, info, out)
        holder, info, out = self.install("c")
        os.remove(os.path.join(holder.root, "game.iso"))
        with self.assertRaisesRegex(RuntimeError, "iso.choose_first"):
            holder._t4_identity_build(self.api, info, out)

    def test_the_iso_is_hashed_once_and_again_when_it_changes(self):
        holder, info, out = self.install("a")
        calls = []
        real = t4_online.hashlib.new

        def counting(name, *args):
            calls.append(name)
            return real(name, *args)
        with mock.patch.object(t4_online.hashlib, "new", side_effect=counting):
            first = holder._t4_identity_build(self.api, info, out).build_id
            t4_online._hash_cache.clear()                                 # a new launcher run: the cache file
            self.assertEqual(holder._t4_identity_build(self.api, info, out).build_id, first)
            self.assertEqual(calls.count("sha256"), 1)
            iso = Path(holder.root, "game.iso")
            iso.write_bytes(b"iso image changed")
            os.utime(iso, ns=(1, 1))
            self.assertNotEqual(holder._t4_identity_build(self.api, info, out).build_id, first)
            self.assertEqual(calls.count("sha256"), 2)


if __name__ == "__main__":
    unittest.main()
