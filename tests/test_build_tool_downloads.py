"""Official-download fallback, with fake assets and installers: never use the network."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp.adapters import build_tool_downloads as tools


class Downloads(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / "build/tmp-home"
        root.mkdir(parents=True, exist_ok=True)
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory(dir=root)))
        self.payload = b"fake installer bytes"
        self.digest = hashlib.sha256(self.payload).hexdigest()
        self.calls = []

    def fetch(self, url, path):
        self.calls.append(url)
        if "api.github.com" in url:
            repo = next(s["repo"] for s in tools.SPECS.values() if s.get("repo") and s["repo"] in url)
            filename = {"git-for-windows/git": "Git-2.55.0-64-bit.exe",
                        "Kitware/CMake": "cmake-4.4.4-windows-x86_64.msi",
                        "ninja-build/ninja": "ninja-win.zip"}[repo]
            asset = dict(name=filename, browser_download_url="https://github.com/" + repo +
                         "/releases/download/v1/" + filename, digest="sha256:" + self.digest)
            Path(path).write_text(json.dumps(dict(assets=[asset])), encoding="utf-8")
        else:
            Path(path).write_bytes(self.payload)

    def check(self, path, signers, digest, run=None):
        self.assertEqual(Path(path).read_bytes(), self.payload)
        self.assertIn(digest, ("", self.digest))
        return self.digest

    def test_official_assets_are_all_verified_before_one_elevation(self):
        jobs = []
        checked = []

        def verify(*args, **kwargs):
            checked.append(args[0])
            return self.check(*args, **kwargs)

        def launch(batch, folder, progress, cancelled, run=None):
            self.assertEqual(len(checked), 4)
            jobs.extend(batch)
            return ["ok"] * len(batch)

        progress = mock.Mock()
        result = tools.install_batch(["git", "cmake", "ninja", "vs2022"], directory=self.folder,
                                     download=self.fetch, verify=verify, elevate=launch, progress=progress)
        self.assertEqual(result, ["ok"] * 4)
        self.assertEqual(len(jobs), 4)
        self.assertEqual(jobs[3]["args"], ["--quiet", "--wait", "--norestart", "--add",
                                          "Microsoft.VisualStudio.Workload.VCTools", "--includeRecommended"])
        self.assertEqual(jobs[3]["signer"], ["Microsoft Corporation"])
        self.assertIn("/VERYSILENT", jobs[0]["args"])
        self.assertIn("ADD_CMAKE_TO_PATH=System", jobs[1]["args"])
        self.assertIn(tools.VS_URL, self.calls)
        self.assertTrue(all(url.startswith("https://") for url in self.calls))
        self.assertEqual(progress.call_args.args, (3, 4, "@t4.tools.vs2022"))
        self.assertTrue(all(not Path(job["path"]).exists() for job in jobs))

    def test_untrusted_asset_never_reaches_elevation(self):
        launch = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, "verification_failed"):
            tools.install_batch(["git"], directory=self.folder, download=self.fetch,
                                verify=mock.Mock(side_effect=RuntimeError("@t4.tools.verification_failed")),
                                elevate=launch)
        launch.assert_not_called()
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_unsigned_ninja_requires_vendor_digest(self):
        def missing_digest(url, path):
            self.fetch(url, path)
            if "api.github.com" in url:
                metadata = json.loads(Path(path).read_text())
                metadata["assets"][0].pop("digest")
                Path(path).write_text(json.dumps(metadata))

        launch = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, "verification_failed"):
            tools.install_batch(["ninja"], directory=self.folder, download=missing_digest,
                                verify=self.check, elevate=launch)
        launch.assert_not_called()
        self.assertEqual(len(self.calls), 1)

    def test_release_cannot_substitute_other_repository(self):
        def substituted(url, path):
            self.fetch(url, path)
            metadata = json.loads(Path(path).read_text())
            metadata["assets"][0]["browser_download_url"] = "https://github.com/attacker/asset.exe"
            Path(path).write_text(json.dumps(metadata))

        with self.assertRaisesRegex(RuntimeError, "download_failed"):
            tools.install_batch(["git"], directory=self.folder, download=substituted,
                                verify=self.check, elevate=mock.Mock())
        self.assertEqual(len(self.calls), 1)

    def test_http_and_unexpected_redirect_hosts_are_rejected(self):
        for url in ("http://github.com/file", "https://evil.example/file", "https://github.com.evil/file",
                    "https://user:password@github.com/file"):
            with self.subTest(url=url), self.assertRaisesRegex(RuntimeError, "download_failed"):
                tools._https(url)
        with self.assertRaisesRegex(RuntimeError, "download_failed"):
            tools._Redirect().redirect_request(None, None, 302, "redirect", {}, "http://github.com/file")

    def test_wrong_architecture_and_unknown_tools_never_download(self):
        fetch = mock.Mock()
        with mock.patch.object(tools.platform, "machine", return_value="ARM64"), \
                self.assertRaisesRegex(RuntimeError, "install_unavailable"):
            tools.install_batch(["git"], download=fetch)
        for ids in (["python"], ["git", "git"], ["msvc", "vs2022"]):
            with self.subTest(ids=ids), self.assertRaisesRegex(RuntimeError, "install_unavailable"):
                tools.install_batch(ids, download=fetch)
        fetch.assert_not_called()

    def test_cancel_before_launch_never_prompts(self):
        launch = mock.Mock()
        cancel = mock.Mock(side_effect=[False, True])
        result = tools.install_batch(["msvc"], directory=self.folder, cancelled=cancel,
                                     download=self.fetch, verify=self.check, elevate=launch)
        self.assertEqual(result, ["cancelled"])
        launch.assert_not_called()

    def test_signature_requires_both_windows_trust_and_exact_publisher(self):
        path = self.folder / "installer.exe"
        path.write_bytes(self.payload)
        run = mock.Mock(return_value=SimpleNamespace(returncode=0, stdout=b"Microsoft Corporation\r\n"))
        with mock.patch.object(tools, "_trust", return_value=True) as trust:
            self.assertEqual(tools.verify(path, ["Microsoft Corporation"], self.digest, run=run), self.digest)
        trust.assert_called_once_with(path)
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertNotIn("shell", run.call_args.kwargs)
        with mock.patch.object(tools, "_trust", return_value=False), \
                self.assertRaisesRegex(RuntimeError, "verification_failed"):
            tools.verify(path, ["Microsoft Corporation"], run=run)
        with mock.patch.object(tools, "_trust", return_value=True), \
                self.assertRaisesRegex(RuntimeError, "verification_failed"):
            tools.verify(path, ["Kitware, Inc."], run=run)

    def test_corrupt_digest_fails_before_signature_check(self):
        path = self.folder / "installer.exe"
        path.write_bytes(self.payload)
        with mock.patch.object(tools, "_trust") as trust, \
                self.assertRaisesRegex(RuntimeError, "verification_failed"):
            tools.verify(path, ["Microsoft Corporation"], "0" * 64)
        trust.assert_not_called()
        self.assertEqual(tools.verify(path, [], self.digest), self.digest)
        with self.assertRaisesRegex(RuntimeError, "verification_failed"):
            tools.verify(path, [])

    def test_signature_cannot_cover_different_bytes(self):
        path = self.folder / "installer.exe"
        path.write_bytes(self.payload)

        def replace_file(*args, **kwargs):
            path.write_bytes(b"replaced")
            return SimpleNamespace(returncode=0, stdout=b"Microsoft Corporation")

        with mock.patch.object(tools, "_trust", return_value=True), \
                self.assertRaisesRegex(RuntimeError, "verification_failed"):
            tools.verify(path, ["Microsoft Corporation"], run=replace_file)

    def test_single_elevated_encoded_worker_uses_fixed_manifest_and_rechecks(self):
        jobs = [dict(id="git", filename="installer.exe", path="C:/fake/installer.exe", sha256=self.digest,
                     signer=["Johannes Schindelin"], args=["/VERYSILENT", "/NORESTART"])]
        run = mock.Mock()

        def fake_installer(command, **kwargs):
            worker = base64.b64decode(command[-1]).decode("utf-16-le")
            self.assertIn(self.digest, worker)
            self.assertLess(worker.index("Copy-Item"), worker.index("Get-FileHash"))
            self.assertLess(worker.index("Get-AuthenticodeSignature"), worker.index("$process=Start-Process"))
            self.assertIn("[Environment]::GetFolderPath('ProgramFiles')", worker)
            self.assertIn("$acl.SetAccessRuleProtection($true,$false)", worker)
            (self.folder / "install-result.json").write_text(json.dumps(dict(states=["ok"], running=False)))
            return SimpleNamespace(returncode=0)

        run.side_effect = fake_installer
        self.assertEqual(tools.elevate(jobs, self.folder, mock.Mock(), lambda: False, run=run), ["ok"])
        run.assert_called_once()
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_uac_cancel_is_clear_error(self):
        run = mock.Mock(return_value=SimpleNamespace(returncode=1223))
        with self.assertRaisesRegex(RuntimeError, "elevation_cancelled"):
            tools.elevate([dict(id="git")], self.folder, mock.Mock(), lambda: False, run=run)

    def test_template_tokens_inside_paths_remain_literal_data(self):
        folder = self.folder / "__MANIFEST____CANCEL____RESULT__"
        folder.mkdir()
        jobs = [dict(id="git", path=str(folder / "git.exe"))]

        def run(command, **kwargs):
            script = base64.b64decode(command[-1]).decode("utf-16-le")
            self.assertIn("$out=" + tools._quote(str(folder / "install-result.json")), script)
            self.assertIn("$cancel=" + tools._quote(str(folder / "cancel")), script)
            self.assertIn("$jobs=ConvertFrom-Json " + tools._quote(json.dumps(jobs)), script)
            (folder / "install-result.json").write_text(json.dumps(dict(states=["ok"], running=False)))
            return SimpleNamespace(returncode=0)

        self.assertEqual(tools.elevate(jobs, folder, mock.Mock(), lambda: False, run=run), ["ok"])

    def test_reboot_preserves_completed_status_and_defers_remaining_tools(self):
        def run(command, **kwargs):
            (self.folder / "install-result.json").write_text(json.dumps(dict(states=["reboot"], running=False)))
            return SimpleNamespace(returncode=0)

        result = tools.elevate([dict(id="vs2022"), dict(id="git")], self.folder, mock.Mock(), lambda: False, run=run)
        self.assertEqual(result, ["reboot", "cancelled"])
        self.assertIn("if($code -in @(3010,1641)) {break}", tools.WORKER)
        self.assertIn("$zip.GetEntry('ninja.exe')", tools.WORKER)
        self.assertIn("Security.Principal.SecurityIdentifier('S-1-5-32-545')", tools.WORKER)
        self.assertIn("$users,'ReadAndExecute'", tools.WORKER)

    def test_worker_failure_and_invalid_result_are_never_success(self):
        for state, error in ((dict(states=[], error="@t4.tools.verification_failed"), "verification_failed"),
                             (dict(states=["unexpected"]), "install_failed"),
                             (dict(states=[]), "install_failed")):
            def run(command, **kwargs):
                (self.folder / "install-result.json").write_text(json.dumps(state))
                return SimpleNamespace(returncode=0)

            with self.subTest(state=state), self.assertRaisesRegex(RuntimeError, error):
                tools.elevate([dict(id="git")], self.folder, mock.Mock(), lambda: False, run=run)

    def test_complete_batch_command_fits_windows_limit(self):
        jobs = []

        def launch(batch, folder, progress, cancelled, run=None):
            jobs.extend(batch)
            return ["ok"] * len(batch)

        tools.install_batch(["git", "cmake", "ninja", "vs2022"], directory=self.folder,
                            download=self.fetch, verify=self.check, elevate=launch)
        script = tools.WORKER.replace("__MANIFEST__", tools._quote(json.dumps(jobs))).replace(
            "__RESULT__", tools._quote(str(self.folder / "install-result.json"))).replace(
            "__CANCEL__", tools._quote(str(self.folder / "cancel")))
        self.assertLess(len(subprocess.list2cmdline(tools._powershell(script))), 32760)

    def test_cancel_during_installer_signals_worker_between_jobs(self):
        import threading
        started = threading.Event()

        def run(command, **kwargs):
            started.set()
            self.assertTrue(started.wait(1))
            # The fake installer waits for the monitoring loop's cancellation file.
            for _ in range(100):
                if (self.folder / "cancel").exists():
                    break
                threading.Event().wait(0.01)
            self.assertTrue((self.folder / "cancel").exists())
            (self.folder / "install-result.json").write_text(json.dumps(dict(states=["ok"], running=False)))
            return SimpleNamespace(returncode=0)

        result = tools.elevate([dict(id="git"), dict(id="cmake")], self.folder, mock.Mock(),
                               lambda: started.is_set(), run=run)
        self.assertEqual(result, ["ok", "cancelled"])
        self.assertIn("if(Test-Path -LiteralPath $cancel) {break}", tools.WORKER)

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell parser")
    def test_generated_worker_parses_without_executing_it(self):
        jobs = [dict(id=name, path=str(self.folder / (name + ".exe")), filename=name + ".exe",
                     sha256=self.digest, signer=spec["signer"], args=spec["args"])
                for name, spec in tools.SPECS.items()]
        script = tools.WORKER.replace("__MANIFEST__", tools._quote(json.dumps(jobs))).replace(
            "__RESULT__", tools._quote(str(self.folder / "result.json"))).replace(
            "__CANCEL__", tools._quote(str(self.folder / "cancel")))
        path = self.folder / "worker.ps1"
        path.write_text(script, encoding="utf-8")
        parser = ("$errors=$null; $tokens=$null; "
                  "[System.Management.Automation.Language.Parser]::ParseFile(" + tools._quote(str(path)) +
                  ",[ref]$tokens,[ref]$errors)|Out-Null; if($errors.Count){$errors|ForEach-Object {$_.Message};exit 1}")
        result = subprocess.run(tools._powershell(parser), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=tools.NO_WINDOW,
                                timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
