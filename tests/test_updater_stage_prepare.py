"""End to end: stage_update then prepare_update, the way the launcher's Update runs them (0.1.4 and 0.1.5 shipped a
stage that prepare could not verify: release.zip was never written). Network is replaced by local bytes."""
import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from openrecomp import updater as u
from tools import release_sign


class StagePrepareTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self.temp, True)
        self.root = Path(self.temp) / "OpenRecomp-FGC"
        self.root.mkdir()
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_HOME=str(Path(self.temp) / "home")))

    def program(self, root, version, channel):
        for item in u.REQUIRED_ITEMS:
            p = root / item
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("fixture", encoding="utf-8")
        (root / "release.json").write_text(json.dumps(dict(project=u.PROJECT, channel=channel.name, version=version)),
                                           encoding="utf-8")

    def run_update(self, with_cache):
        seed = os.urandom(32)
        public = release_sign.public_key(seed)
        base = u.configured_channel()
        channel = u.Channel(base.repository, base.repository_id, base.name, (public.hex(),))
        self.program(self.root, "v1.0.0", channel)
        src = Path(self.temp) / "src"
        src.mkdir(exist_ok=True)
        self.program(src, "v1.2.3", channel)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for f in src.rglob("*"):
                if f.is_file():
                    z.write(f, u.ARCHIVE_TOP + "/" + f.relative_to(src).as_posix())
        data = buf.getvalue()
        digest = hashlib.sha256(data).hexdigest()
        sums = (digest + "  OpenRecomp-v1.2.3.zip\n").encode("ascii")
        sig = json.dumps(dict(algorithm="ed25519", channel=channel.name, version="v1.2.3",
                              key_id=hashlib.sha256(public).hexdigest()[:16],
                              signature=release_sign.sign(seed, u.signature_message(channel.name, "v1.2.3", sums)).hex()
                              )).encode("utf-8")
        release = dict(version="v1.2.3", size=len(data), digest=digest, zip_url="zip", sums_url="sums", sig_url="sig")
        if with_cache:
            work = u._work_root(self.root)
            work.mkdir(parents=True, exist_ok=True)
            (work / u.cache_name("v1.2.3")).write_bytes(data)

        def fake_download(url, channel_, limit, destination=None, progress=None, cancel=None):
            payload = {"zip": data, "sums": sums, "sig": sig}[url]
            if destination is None:
                return payload
            Path(destination).write_bytes(payload)
            return len(payload)
        with mock.patch.object(u, "_download", side_effect=fake_download):
            staged = u.stage_update(self.root, release, channel)
            u.prepare_update(self.root, staged, channel)       # must authenticate what stage_update kept

    def test_fresh_download(self):
        self.run_update(with_cache=False)

    def test_from_the_cached_download(self):
        self.run_update(with_cache=True)


if __name__ == "__main__":
    unittest.main()
