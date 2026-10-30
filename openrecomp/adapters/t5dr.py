"""Tekken 5 DR: the installed T5DR Online's own Python (launcher/core.py, replays.py, lobby/t5lobby) does the work.

Nothing of it is copied: OpenRecomp-FGC imports it from the player's install. Pictures come from that install's cache
(read from the player's own built game by fighter_art.py) and stay on the PC.
"""
import collections
import glob
import importlib
import json
import os
import queue
import re
import subprocess
import threading

from .base import Adapter, NO_WINDOW, add_path, expand_locations
from ..manifest import art_dir

DISPLAY = [("window", "Fenster"), ("window1080", "Fenster 1080p"), ("window1440", "Fenster 1440p"),
           ("maximized", "Maximiert"), ("borderless", "Randlos")]
RES_NAMES = {"lowest": "Niedrigste (0.5x)", "lower": "Niedrig (0.75x)", "native": "Nativ (720p)", "1080p": "1080p",
             "1440p": "1440p", "4k": "4K", "auto": "Auto"}
ON_OFF = [("on", "An"), ("off", "Aus")]
YES_NO = [(False, "Aus"), (True, "An")]
RANK_TAG = re.compile(r"\s*\[\d+\]$")


def version_key(root):
    try:
        with open(os.path.join(root, "release.json"), encoding="utf-8") as f:
            parts = json.load(f).get("version", "0").split(".")
        return tuple(int(p) for p in parts)
    except (OSError, ValueError, AttributeError):
        return (0,)


def find_root(manifest, config):
    """The newest installed T5DR Online with a built game; else the newest install."""
    chosen = (config.get("roots") or {}).get(manifest["id"]) or os.environ.get("OPENRECOMP_T5DR_ROOT")
    if chosen:
        return chosen if os.path.isfile(os.path.join(chosen, "launcher", "core.py")) else None
    found = [p for p in expand_locations(manifest.get("locations", []))
             if os.path.isfile(os.path.join(p, "launcher", "core.py"))]
    if not found:
        return None
    built = [p for p in found if os.path.isfile(os.path.join(p, "runtime", "t5dr.exe"))]
    return max(built or found, key=version_key)


class T5DR(Adapter):
    native_label = "T5DR-Online-Launcher"

    def __init__(self, manifest, config, root, core=None, replays_mod=None):
        super().__init__(manifest, config)
        self.root = root
        if core is None:
            add_path(os.path.join(root, "lobby"))
            add_path(os.path.join(root, "tools"))
            add_path(os.path.join(root, "launcher"))
            core = importlib.import_module("core")
            replays_mod = importlib.import_module("replays")
        self.core = core
        self.rp = replays_mod
        self.s = core.Settings()
        self.game = None
        self.build = None
        self.build_steps = {}
        self.build_step = ""
        self.build_fraction = 0.0
        self.build_line = ""
        self.last_result = ""
        self._state = None
        self._replays = None
        self._fighters = None
        self._hero_busy = False

    def found(self):
        return True

    def state(self, fresh=False):
        if self._state is None or fresh:
            self._state = self.core.game_state(self.s.out_dir)
        return self._state

    def ready(self):
        return bool(self.state()["ok"])

    def release(self):
        try:
            with open(os.path.join(self.root, "release.json"), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def status(self):
        st = self.state()
        entries = self.replay_entries()
        last = entries[0].when.strftime("%d.%m., %H:%M") if entries and entries[0].when else "Noch nie"
        version = self.release().get("version") or "Entwicklung"
        if st["ok"]:
            status, detail = "Bereit", "Dein Spiel läuft lokal auf diesem PC. Den Charakter wählst du im Spiel."
        elif st["needs_rebuild"]:
            status, detail = "Neu bauen", "Diese Version ändert den Spielcode: einmal bauen, etwa 2 Minuten."
        else:
            status, detail = "Noch nicht gebaut", "Wähle dein Paket und deine Lizenz im Build-Bereich."
        return dict(status=status, version=f"v{version}", players="Lobby und Ranked", last=last, detail=detail)

    # ---------------------------------------------------------------- pictures
    def face(self, gid):
        path = os.path.join(self.s.out_dir, "cache", "fighters", f"face_{gid:02d}.png")
        return path if os.path.isfile(path) else ""

    def hero(self):
        """The full-figure render of the player's main, read once from their own game into the user folder."""
        gid = self.main_id()
        if gid is None:
            gid = 9                                  # Jin
        path = os.path.join(art_dir("t5dr"), f"hero_{gid:02d}.png")
        if os.path.isfile(path):
            return path
        if not self._hero_busy and self.state()["built"]:
            self._hero_busy = True
            threading.Thread(target=self._make_hero, args=(gid, path), daemon=True).start()
        return ""

    def _make_hero(self, gid, path):
        try:
            fa = importlib.import_module("t5lobby.fighter_art")
            src = fa.ra.find_sources(self.s.out_dir)
            if not src:
                return
            dxt = fa.render_dxt(*src, gid, rows=fa.TEX_W)
            rgba = fa.dxt5_square(dxt, fa.TEX_W, 0, 0, fa.TEX_W)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            fa._write(path, fa.ra.png_bytes(rgba, fa.TEX_W, fa.TEX_W))  # noqa: SLF001 -- the module's atomic write
        except Exception as e:  # noqa: BLE001 -- a missing picture must never stop the launcher
            self.problem = f"Bild nicht gelesen: {e}"

    # ---------------------------------------------------------------- playing
    def start(self, extra_env=None):
        if not self.ready():
            raise RuntimeError(self.status()["detail"])
        if self.running():
            raise RuntimeError("Das Spiel läuft schon.")
        self.game = self.core.GameRun(self.s.out_dir, self.s)
        return self.game.start(extra_env=extra_env)

    def running(self):
        return bool(self.game and self.game.running())

    def stop(self):
        if self.game:
            self.game.stop()

    def _exe_launcher(self, *args):
        exe = os.path.join(self.root, "T5DR Online.exe")
        if os.path.isfile(exe):
            cmd = [exe]
        else:
            script = os.path.join(self.root, "launcher", "t5dr_launcher.pyw")
            cmd = [self.core.sys.executable, script]
        return subprocess.Popen(cmd + list(args), cwd=self.root, creationflags=NO_WINDOW)

    def open_native(self):
        self._exe_launcher()

    # ---------------------------------------------------------------- settings
    def settings(self):
        s = self.s
        res = [(k, RES_NAMES.get(k, k)) for k in self.core.INTERNAL_RES_LABELS]
        delay = [("auto", "Auto"), ("0", "0 Frames"), ("1", "1 Frame"), ("2", "2 Frames")]
        return [
            dict(id="display", label="Anzeige", options=DISPLAY, value=s["display"],
                 hint="Wie das Spielfenster aufgeht. Im Spiel gehen auch F11 und Alt+Enter.",
                 lead="Randlos füllt den Bildschirm, im Fenster bleibt der PC nebenher nutzbar."),
            dict(id="internal_res", label="Interne Auflösung", options=res, value=s["internal_res"],
                 hint="Wie scharf das Spiel gerendert wird.",
                 lead="Höhere Stufen brauchen mehr Grafikleistung. Online darf jeder eine andere Stufe nutzen."),
            dict(id="vsync", label="V-Sync", options=ON_OFF, value=s["vsync"],
                 hint="Aus: am wenigsten Lag, das Bild kann reissen.", lead="Betrifft nur, wie das Bild auf den Bildschirm kommt."),
            dict(id="shadows", label="Schatten", options=ON_OFF, value=s["shadows"],
                 hint="Schatten von Kämpfern und Stage.", lead="Aus entlastet schwache Grafikkarten."),
            dict(id="effects", label="Effekte", options=ON_OFF, value=s["effects"],
                 hint="Trefferfunken, Flammen, Rauch, Nebel, Wasserfälle.", lead="Aus entlastet schwache Grafikkarten."),
            dict(id="stage_blur", label="Stage-Unschärfe", options=ON_OFF, value=s["stage_blur"],
                 hint="Weichzeichner und Leuchten mancher Stages.", lead="Reine Optik, online ohne Einfluss."),
            dict(id="input_delay", label="Online Input-Delay", options=delay, value=str(s["input_delay"]),
                 hint="Auto wählt nach Ping. Beide Spieler stellen ihn ein.", lead="Mehr Delay heisst weniger Rollback. Ranked legt der Server fest."),
            dict(id="training", label="Training-Anzeige", options=[("off", "Aus"), ("inputs", "Eingaben"), ("frames", "Eingaben + Frames")],
                 value=s["training"], hint="Eingaben und Frame-Daten im Practice-Modus. F2 wechselt im Spiel.", lead="Zeigt Startup und Vorteil jedes Moves."),
            dict(id="practice", label="Practice-Werkzeuge", options=YES_NO, value=bool(s["practice"]),
                 hint="SELECT-Kombis, Dummy und Aufnahmen im Practice-Modus.", lead="Nur offline im Practice-Modus."),
            dict(id="always_left", label="Immer links", options=YES_NO, value=bool(s["always_left"]),
                 hint="Als P2 zeigt dieser PC den Kampf gespiegelt, du stehst links.", lead="Nur die Anzeige auf diesem PC ändert sich."),
            dict(id="mute", label="Ton aus", options=YES_NO, value=bool(s["mute"]), hint="Schaltet den Spielton stumm.", lead="Schaltet den Spielton stumm."),
            dict(id="replays", label="Replays speichern", options=YES_NO, value=bool(s["replays"]),
                 hint="Online-Matches landen als Replay auf diesem PC.", lead="Ein Match braucht nur wenige KB."),
            dict(id="unlock_stages", label="Alte Stages offline", options=YES_NO, value=bool(s["unlock_stages"]),
                 hint="Tekken-5-Stages ohne Arcade-Durchlauf. Der Spielstand bleibt.", lead="Nur offline."),
            dict(id="unlock_items", label="Items gratis offline", options=YES_NO, value=bool(s["unlock_items"]),
                 hint="Alle Items im Shop kostenlos. Der Spielstand wird vorher gesichert.", lead="Nur offline."),
        ]

    def set_setting(self, sid, value):
        self.s[sid] = value
        if sid == "internal_res":
            self.s["internal_res_set"] = True
        self.s.save()

    def quick_settings(self):
        return ["display", "internal_res"]

    def text_value(self, tid):
        return self.s["nickname"] if tid == "nickname" else ""

    def set_text_value(self, tid, value):
        if tid == "nickname":
            self.s["nickname"] = value
            self.s.save()

    # ---------------------------------------------------------------- online: the T5DR launcher runs the lobby
    def online_items(self):
        chosen = self.fighter_name(self.chosen_fighter())
        main = self.fighter_name_id(self.main_id())
        return [
            dict(kind="heading", label="Dein Charakter"),
            dict(kind="action", id="fighter", label="Charakter", value=chosen, verb="Ändern", opens="fighters",
                 hint="Gilt, wenn du im Spiel nicht rechtzeitig wählst.",
                 detail=dict(kicker="Dein Charakter", title=chosen, image=self.fighter_image(self.chosen_fighter()),
                             lead="Nach dem Matchfund wählst du im Spiel selbst (30 s, Select = Zufall). Der Charakter hier gilt, wenn du nicht rechtzeitig wählst.",
                             rows=[dict(k="Dein Main", v=main or "noch keiner"),
                                   dict(k="Kostüm", v="Bestätigen-Taste im Spiel"), dict(k="Im Ranked-Set", v="Hier gesperrt")])),
            dict(kind="heading", label="Spielen", mt=12),
            dict(kind="action", id="ranked", label="Ranked", verb="Suchen",
                 hint="Die Suche läuft im T5DR-Launcher, OpenRecomp-FGC öffnet ihn dafür.",
                 detail=dict(kicker="T5DR Online", title="Ranked", lead="Wertet für deinen Rang. Die Suche läuft im T5DR-Launcher, dort siehst du Match und Ready-Check.",
                             rows=[dict(k="Modus", v="Best of 3"), dict(k="Seiten", v="Vom Server"), dict(k="Stage", v="Zufall")], primary="Suchen")),
            dict(kind="action", id="casual", label="Quick Match", verb="Suchen",
                 hint="Die Suche läuft im T5DR-Launcher, OpenRecomp-FGC öffnet ihn dafür.",
                 detail=dict(kicker="T5DR Online", title="Quick Match", lead="Ungewertet, nach Ping. Die Suche läuft im T5DR-Launcher.",
                             rows=[dict(k="Wertung", v="Keine"), dict(k="Rematch", v="Ja")], primary="Suchen")),
            dict(kind="action", id="lobby", label="Lobby, Räume, Freunde", verb="Öffnen",
                 hint="Der T5DR-Launcher mit Lobby, Räumen, Turnieren, Freunden und Rangliste.",
                 detail=dict(kicker="T5DR Online", title="Lobby", lead="Räume, Turniere, Freunde, Zuschauen und Rangliste laufen weiter im T5DR-Launcher.",
                             rows=[dict(k="Stand", v="Noch nicht in OpenRecomp-FGC")], primary="Öffnen")),
            dict(kind="action", id="nickname", label="Spielername", value=self.s["nickname"] or "keiner", verb="Ändern", opens="text:nickname",
                 hint="Dein Name für die Lobby. Die Bildschirmtastatur reicht völlig.",
                 detail=dict(kicker="Dein Profil", title="Spielername", lead="So siehst du in der Lobby aus.", rows=[dict(k="Aktuell", v=self.s["nickname"] or "keiner")])),
        ]

    def search_on_start_works(self):
        """Up to 1.1.9 `--search` asks for the game's state before the launcher has read it and always says "build first"."""
        return version_key(self.root) > (1, 1, 9)

    def run_online(self, item_id):
        if item_id in ("ranked", "casual"):
            name = "Ranked" if item_id == "ranked" else "Quick Match"
            if self.search_on_start_works():
                self._exe_launcher("--search", item_id)
                return f"T5DR-Launcher startet die Suche: {name}."
            self._exe_launcher()
            return f"T5DR-Launcher öffnet sich. Starte {name} dort."
        if item_id == "lobby":
            self._exe_launcher()
            return "T5DR-Launcher öffnet sich."
        return ""

    # ---------------------------------------------------------------- fighters
    def _fighter_table(self):
        if self._fighters is None:
            path = os.path.join(self.root, "lobby", "t5lobby", "data", "fighters.json")
            try:
                with open(path, encoding="utf-8") as f:
                    self._fighters = json.load(f)["fighters"]
            except (OSError, ValueError, KeyError):
                self._fighters = []
        return self._fighters

    def fighters(self):
        picks = [f for f in self._fighter_table() if not f.get("boss") and not f.get("unverified")]
        picks.sort(key=lambda f: f["name"].casefold())
        return [dict(key=f["key"], name=f["name"], image=self.face(f["id"])) for f in picks]

    def fighter_name(self, key):
        return next((f["name"] for f in self._fighter_table() if f["key"] == key), "Zufall")

    def fighter_name_id(self, gid):
        return next((f["name"] for f in self._fighter_table() if f["id"] == gid), "")

    def fighter_image(self, key):
        gid = next((f["id"] for f in self._fighter_table() if f["key"] == key), None)
        return self.face(gid) if gid is not None else ""

    def online_cfg_path(self):
        base = os.environ.get("T5_ONLINE_DIR")
        if base:
            return os.path.join(base, "online.json")
        return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "T5DROnline", "online.json")

    def _online_cfg(self):
        try:
            with open(self.online_cfg_path(), encoding="utf-8") as f:
                cfg = json.load(f)
            return cfg if isinstance(cfg, dict) else {}
        except (OSError, ValueError):
            return {}

    def chosen_fighter(self):
        return self._online_cfg().get("char") or "random"

    def set_fighter(self, key):
        """The same field of the same file the T5DR launcher's character grid writes; the rest stays as it is."""
        cfg = self._online_cfg()
        cfg["char"] = key
        path = self.online_cfg_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".openrecomp.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=1)
        os.replace(tmp, path)

    def main_id(self):
        """The fighter of most of this PC's replays (the lobby's "main" needs a login)."""
        counts = collections.Counter()
        for e in self.replay_entries():
            gid = e.p1 if e.slot == 0 else e.p2
            if isinstance(gid, int):
                counts[gid] += 1
        return counts.most_common(1)[0][0] if counts else None

    def main_fighter(self):
        return self.fighter_name_id(self.main_id())

    def recent_results(self):
        out = []
        for e in self.replay_entries():
            if e.complete and e.won is not None:
                out.append("S" if e.won else "N")
            if len(out) == 5:
                break
        return out

    # ---------------------------------------------------------------- replays
    def replay_entries(self):
        if self._replays is None:
            try:
                self._replays = self.rp.list_replays(self.s.replay_dir)
            except OSError:
                self._replays = []
        return self._replays

    def replays(self):
        out = []
        for i, e in enumerate(self.replay_entries()):
            a, b = self.rp.fighter_name(e.p1), self.rp.fighter_name(e.p2)
            score = f"{e.score[0]}:{e.score[1]}" if e.score else ""
            result = ("Sieg " if e.won else "Niederlage ") + score if e.won is not None else (score or "Offen")
            opponent = RANK_TAG.sub("", e.opponent or "") or "Unbekannt"
            when = e.when.strftime("%d.%m.%Y, %H:%M") if e.when else "?"
            out.append(dict(id=str(i), label=f"{a} – {b}", when=e.when.strftime("%H:%M") if e.when else "",
                            date=when, group=f"{e.when.strftime('%d.%m.') if e.when else '?'} · {opponent}", opponent=opponent,
                            netcode="Rollback" if e.mode == "rollback" else "Lockstep", result=result,
                            images=[self.face(e.p1), self.face(e.p2)]))
        return out

    def play_replay(self, replay_id, extra_env=None):
        e = self.replay_entries()[int(replay_id)]
        env = self.rp.playback_env(e.path, match=e.index)
        env.update(extra_env or {})
        return self.start(extra_env=env)

    # ---------------------------------------------------------------- build
    def sources(self):
        home = os.path.expanduser("~")
        dirs = [os.path.dirname(self.s["pkg"]) if self.s["pkg"] else "", os.path.join(home, "Downloads"), os.path.join(home, "Desktop"), self.root]
        dirs = [d for d in dirs if d]
        pkg_ok, _level, pkg_text = self.core.describe_pkg(self.s["pkg"], self.s.out_dir) if self.s["pkg"] else (False, "", "")
        rap = self.s["rap"]
        rap_ok = bool(rap) and os.path.isfile(rap)
        return [
            dict(id="pkg", label="Paket (.pkg)", value="Gefunden" if pkg_ok else "Fehlt", ok=pkg_ok, kind="file", exts=[".pkg"], dirs=dirs,
                 hint="Dein Spielpaket aus deinem Konto. Nichts verlässt diesen PC.", note=pkg_text),
            dict(id="rap", label="Lizenz (.rap)", value="Gefunden" if rap_ok else "Fehlt", ok=rap_ok, kind="file", exts=[".rap"], dirs=dirs,
                 hint="Deine Lizenzdatei aus deinem Konto. Nichts verlässt diesen PC.", note=""),
        ]

    def set_source(self, sid, path):
        self.s[sid] = path
        self.s.save()
        self._state = None
        return ""

    def build_options(self):
        return [dict(id="low_priority", label="PC reaktionsfähig halten", options=YES_NO, value=bool(self.s["low_priority"]),
                     hint="Der Build läuft langsamer, der PC bleibt nutzbar.", lead="Der Build läuft langsamer, dafür bleibt der PC nebenher gut nutzbar.")]

    def build_ready(self):
        if not self.s["pkg"] or not self.s["rap"]:
            return "Wähle zuerst Paket und Lizenz."
        return ""

    def build_start(self, force=False):
        self.build_steps = {}
        self.build_step = ""
        self.build_fraction = 0.0
        self.last_result = ""
        self.build = self.core.BuildRun(self.s["pkg"], self.s["rap"], self.s.out_dir, force=force, low_priority=bool(self.s["low_priority"]))
        own_python = os.path.join(self.root, "python", "python.exe")      # the build's tools run on the install's Python
        if os.path.isfile(own_python):
            self.build.cmd[0] = own_python
        self.build.start()

    def _pump_build(self):
        if not self.build:
            return
        while True:
            try:
                ev = self.build.events.get_nowait()
            except queue.Empty:
                return
            kind, value = ev[0], ev[1] if len(ev) > 1 else None
            if kind == "step":
                if self.build_step:
                    self.build_steps[self.build_step] = "Fertig"
                self.build_step = value
                self.build_steps[value] = "Läuft"
            elif kind == "skip":
                self.build_steps[value] = "Fertig"
            elif kind == "sub":
                self.build_fraction = float(value)
            elif kind == "line":
                self.build_line = str(value)
            elif kind == "error":
                self.last_result = str(value)
            elif kind == "end":
                if value == 0:
                    if self.build_step:
                        self.build_steps[self.build_step] = "Fertig"
                    self.last_result = "Fertig gebaut."
                elif value == -1:
                    self.last_result = "Abgebrochen."
                elif not self.last_result:
                    self.last_result = f"Der Build ist fehlgeschlagen. Log: {self.build.log_path}"
                self.build = None
                self._state = None

    def build_state(self):
        self._pump_build()
        names = list(self.core.STEP_TITLES)
        steps = [dict(k=self.core.STEP_TITLES[n], v=self.build_steps.get(n, "Offen")) for n in names]
        done = sum(1 for n in names if self.build_steps.get(n) == "Fertig")
        return dict(running=self.build is not None, fraction=done / len(names) if names else 0.0,
                    title=self.core.STEP_TITLES.get(self.build_step, ""), steps=steps, result=self.last_result, line=self.build_line)

    def build_cancel(self):
        if self.build:
            self.build.cancel()


def installed_copies(manifest):
    return [p for loc in manifest.get("locations", []) for p in glob.glob(os.path.expandvars(loc))]
