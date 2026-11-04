"""The installed T5DR launcher's local checks and report writer; no upload path."""
import importlib.util
import os
import sys
import threading

from .t5_coexist import readonly_imports


FINDINGS = {
    "package_version": ("@support.finding.package_version.title", "@support.finding.package_version.fix"),
    "package_damaged": ("@support.finding.package_damaged.title", "@support.finding.package_damaged.fix"),
    "unpack_memory": ("@support.finding.unpack_memory.title", "@support.finding.unpack_memory.fix"),
    "eu_offline": ("@support.finding.eu_offline.title", "@support.finding.eu_offline.fix"),
    "gpu_tier1": ("@support.finding.gpu_tier1.title", "@support.finding.gpu_tier1.fix"),
    "two_cores": ("@support.finding.two_cores.title", "@support.finding.two_cores.fix"),
    "wine": ("@support.finding.wine.title", "@support.finding.wine.fix"),
    "wine_graphics": ("@support.finding.wine_graphics.title", "@support.finding.wine_graphics.fix"),
    "firewall": ("@support.finding.firewall.title", "@support.finding.firewall.fix"),
}


class T5Support:
    def _support_import(self, name):
        path = os.path.realpath(os.path.join(self.root, "launcher", name + ".py"))
        if not os.path.isfile(path):
            raise ImportError("@support.unavailable")
        cached = sys.modules.get(name)
        if cached is not None:
            if os.path.normcase(os.path.realpath(getattr(cached, "__file__", ""))) != os.path.normcase(path):
                raise ImportError("@support.unavailable")
            return cached
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            with readonly_imports():
                spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(name, None)
            raise
        return module

    def _support_runtime(self):
        modules = getattr(self, "_support_modules", None)
        if modules is None:
            # problem_check imports problem_report by name; load and verify that dependency first.
            cached = sys.modules.get("replays")
            expected = os.path.realpath(os.path.join(self.root, "launcher", "replays.py"))
            if cached is not None and os.path.normcase(os.path.realpath(getattr(cached, "__file__", ""))) != os.path.normcase(expected):
                raise ImportError("@support.unavailable")
            report = self._support_import("problem_report")
            check = self._support_import("problem_check")
            modules = self._support_modules = (check, report)
        return modules

    def support_available(self):
        try:
            check, report = self._support_runtime()
            return (callable(getattr(check, "check", None))
                    and all(callable(getattr(report, name, None))
                            for name in ("Context", "settings_lines", "build_info_for", "discover", "build"))
                    and callable(getattr(self.core, "desktop_dir", None)))
        except Exception:  # a missing optional module never prevents launching the game
            return False

    def support_state(self):
        state = getattr(self, "_support_status", None)
        if state is None:
            state = dict(running=False, operation="", checked=False, findings=[], report="", error="")
        return dict(state, findings=[dict(f) for f in state["findings"]])

    def support_start(self, kind="check"):
        if kind not in ("check", "report") or not self.support_available():
            raise RuntimeError("@support.unavailable")
        state = self.support_state()
        if state["running"]:
            return False
        state.update(running=True, operation=kind, error="")
        self._support_status = state
        try:
            threading.Thread(target=self._support_work, args=(kind,), daemon=True).start()
        except Exception as e:
            state.update(running=False, error=self.message("support.failed", error=str(e)))
            self._support_status = state
            return False
        return True

    def _support_work(self, kind):
        state = self.support_state()
        try:
            check, report = self._support_runtime()
            if kind == "check":
                findings = []
                for finding in check.check(self.s.out_dir):
                    label, fix = FINDINGS.get(finding.key, ("@support.finding.unknown.title", "@support.finding.unknown.fix"))
                    findings.append(dict(id=finding.key, label=label, seen="", fix=fix,
                                         kind=getattr(finding, "kind", "problem")))
                state.update(checked=True, findings=findings)
            else:
                dest = self.core.desktop_dir()
                # Reports belong to the player's folder, never the public launcher checkout.
                checkout = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
                if not dest or not os.path.isabs(dest):
                    raise RuntimeError("@support.unavailable")
                dest = os.path.realpath(dest)
                try:
                    inside_checkout = os.path.commonpath((checkout, dest)) == checkout
                except ValueError:  # the player's Desktop can be on another drive
                    inside_checkout = False
                if inside_checkout:
                    raise RuntimeError("@support.unavailable")
                release = self.release()
                context = report.Context(
                    self.s.out_dir, root=self.root,
                    launcher_log=os.path.join(self.root, "launcher.log"),
                    settings_lines=report.settings_lines(self.s, out_dir=self.s.out_dir),
                    release=release,
                    build_info=lambda: report.build_info_for(self.s.out_dir, release, self.root),
                    online_dir=os.path.dirname(self.online_cfg_path()))
                groups = report.discover(context)
                result = report.build(context, dest, groups=groups)
                state.update(report=result.path)
        except Exception as e:  # the UI keeps the last findings and lets the player retry
            state["error"] = self.message("support.failed", error=str(e))
        state["running"] = False
        self._support_status = state
