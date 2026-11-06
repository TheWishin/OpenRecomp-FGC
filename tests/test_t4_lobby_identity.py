"""The T4 lobby identity holds what Direct IP's check holds: build id fields, compiler and game files, and the ELF.

Review t4-online-b740a3a finding 1; 0.1.3: the game files extracted from the ISO (game\\disc: SLUS_203.28,
TEKKEN\\DATA.BIN, IRX\\IOPRP243.IMG) replace the whole ISO file, so two clean rips of SLUS-20328 pair. Test files
only (no game data, no server): the lobby server recomputes the id from elf/code/net as before
(BuildInfo.wire_id), so builds that differ only in compiler or game files get different ids.
"""
import hashlib
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

    def install(self, name, elf=b"elf v1", data=b"data bin", irx=b"ioprp", iso=b"iso image",
                compiler=("Clang", "23.1.3")):
        root = self.dir / name
        disc = root / "game" / "disc"
        (disc / "TEKKEN").mkdir(parents=True)
        (disc / "IRX").mkdir()
        (disc / "SLUS_203.28").write_bytes(elf)
        (disc / "TEKKEN" / "DATA.BIN").write_bytes(data)
        (disc / "IRX" / "IOPRP243.IMG").write_bytes(irx)
        out = root / "bin"
        out.mkdir()
        (out / "t4net_build.json").write_text(json.dumps(dict(
            id="0" * 16, toolchain=["CXX_ID=" + compiler[0], "CXX_VERSION=" + compiler[1], "GENERATOR=Ninja"])),
            encoding="utf-8")
        (root / "game.iso").write_bytes(iso)
        info = BuildInfo(hashlib.sha1(b"elf v1").hexdigest(), CODE, "0.1.3")
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
        self.assertNotEqual(a.build_id, BuildInfo(a.elf_sha1, CODE, "0.1.3").build_id)

    def test_two_rips_with_the_same_game_files_pair(self):
        """Another ISO file (other padding, other dump tool) but the same extracted files: the same id (0.1.3)."""
        self.assertEqual(self.ident("a", iso=b"rip one").build_id, self.ident("b", iso=b"rip two, other bytes").build_id)

    def test_the_folder_and_the_launcher_copy_do_not_matter(self):
        short = self.ident("x").build_id
        deep = self.ident(os.path.join("Very Long Folder Name", "Another Deep Folder", "Tekken 4")).build_id
        self.assertEqual(short, deep)

    def test_another_compiler_or_other_game_files_is_another_build(self):
        base = self.ident("a").build_id
        self.assertNotEqual(self.ident("b", compiler=("MSVC", "19.51.36000.0")).build_id, base)
        self.assertNotEqual(self.ident("c", data=b"another data.bin").build_id, base)
        self.assertNotEqual(self.ident("d", irx=b"another irx").build_id, base)

    def test_a_stale_elf_a_stamp_without_compiler_or_missing_game_files_is_refused(self):
        holder, info, out = self.install("a", elf=b"elf v0")
        with self.assertRaisesRegex(RuntimeError, "t4.direct_identity_failed"):
            holder._t4_identity_build(self.api, info, out)
        holder, info, out = self.install("b")
        Path(out, "t4net_build.json").write_text(json.dumps(dict(id="0" * 16, toolchain=[])), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "t4.direct_identity_failed"):
            holder._t4_identity_build(self.api, info, out)
        holder, info, out = self.install("c")
        os.remove(os.path.join(holder.root, "game", "disc", "TEKKEN", "DATA.BIN"))
        with self.assertRaisesRegex(RuntimeError, "online.build_required"):
            holder._t4_identity_build(self.api, info, out)

    def test_no_iso_needed_once_the_game_is_built(self):
        holder, info, out = self.install("a")
        os.remove(os.path.join(holder.root, "game.iso"))
        self.assertRegex(holder._t4_identity_build(self.api, info, out).build_id, r"^[0-9a-f]{16}$")

    def test_the_refusals_reach_the_player_as_their_own_texts(self):
        from test_t4_online import Subject
        subject = Subject(str(self.dir))
        self.addCleanup(subject.online_close)
        for key in ("@t4.direct_identity_failed", "@online.build_required"):
            self.assertEqual(subject._online_error(RuntimeError(key)), key)

    def test_the_game_files_are_hashed_once_and_again_when_they_change(self):
        holder, info, out = self.install("a")
        data = os.path.join(holder.root, "game", "disc", "TEKKEN", "DATA.BIN")
        reads = []
        real = open

        def counting(path, *args, **kwargs):
            if os.path.normcase(str(path)) == os.path.normcase(data):
                reads.append(path)
            return real(path, *args, **kwargs)
        with mock.patch("builtins.open", side_effect=counting):
            first = holder._t4_identity_build(self.api, info, out).build_id
            t4_online._hash_cache.clear()                                 # a new launcher run: the cache file
            self.assertEqual(holder._t4_identity_build(self.api, info, out).build_id, first)
            self.assertEqual(len(reads), 1)
            Path(data).write_bytes(b"data bin changed")
            os.utime(data, ns=(1, 1))
            self.assertNotEqual(holder._t4_identity_build(self.api, info, out).build_id, first)
            self.assertEqual(len(reads), 2)

    def test_the_builds_own_record_is_used_while_size_and_time_match(self):
        """T4 0.1.3's build writes game/t4-game-files.json: the first Online login does not read DATA.BIN again."""
        holder, info, out = self.install("a")
        expected = holder._t4_identity_build(self.api, info, out).build_id
        disc = Path(holder.root, "game", "disc")
        files = {}
        for name in ("SLUS_203.28", "TEKKEN/DATA.BIN", "IRX/IOPRP243.IMG"):
            path = disc / name
            files[name] = dict(size=path.stat().st_size, mtime_ns=path.stat().st_mtime_ns,
                               sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        Path(holder.root, "game", "t4-game-files.json").write_text(json.dumps(dict(schema=1, files=files)), encoding="utf-8")
        t4_online._hash_cache.clear()
        data = str(disc / "TEKKEN" / "DATA.BIN")
        real = open
        with mock.patch("builtins.open", side_effect=lambda path, *a, **k: (_ for _ in ()).throw(AssertionError("read"))
                        if os.path.normcase(str(path)) == os.path.normcase(data) else real(path, *a, **k)):
            with mock.patch.dict(os.environ, OPENRECOMP_HOME=str(self.dir / "fresh-home")):
                self.assertEqual(holder._t4_identity_build(self.api, info, out).build_id, expected)
        # a changed file (other time) is hashed again, never taken from the record
        os.utime(data, ns=(5, 5))
        t4_online._hash_cache.clear()
        with mock.patch.dict(os.environ, OPENRECOMP_HOME=str(self.dir / "fresh-home2")):
            self.assertEqual(holder._t4_identity_build(self.api, info, out).build_id, expected)

    def test_the_formula_is_the_direct_ip_preflight_formula(self):
        """tools/net_preflight.py (T4) hashes the same three files the same way: Direct IP and the lobby agree."""
        holder, _info, _out = self.install("a")
        expected = hashlib.sha256(b"t4-game-files-v1\n")
        for name, content in (("SLUS_203.28", b"elf v1"), ("TEKKEN/DATA.BIN", b"data bin"), ("IRX/IOPRP243.IMG", b"ioprp")):
            expected.update(name.encode() + b"\0" + hashlib.sha256(content).hexdigest().encode() + b"\n")
        self.assertEqual(t4_online.game_files_sha256(holder.root), expected.hexdigest())


if __name__ == "__main__":
    unittest.main()
