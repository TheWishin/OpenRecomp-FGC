"""Install / update progress that outlives its dialog (0.1.5).

The progress dialog is modal: while it is open nothing behind it reacts. Its default action is Hide; Cancel is only
there while stopping is still safe (looking up, downloading, verifying, unpacking before the end). Hiding closes the
dialog and the work goes on; a small card at the bottom right then shows one line per running job (both games, the
launcher's own update), for a few seconds after a job ends (a failure stays until it is opened), and reopens the
dialog. While a game's update runs, that game's Play / Build / Online actions say "Update running"."""
from . import i18n
from .nav_game_setup import STEP_TEXT, UPDATE_STEP_TEXT

END_SECONDS = 6.0               # a finished or cancelled job stays on the card this long; a failed one until opened
LAUNCHER = "launcher"           # a job's id: the launcher's own update; a game's job id is the game's id


def game_busy(phase):
    return phase in ("installing", "updating")


def launcher_busy(phase):
    return phase in ("installing", "waiting")


def launcher_dialog_busy(phase):
    return phase in ("checking", "installing", "waiting")


def cancel_safe(st):
    """True while stopping changes nothing: before the files are put in place. At 100 % unpack the exchange follows."""
    if st.get("cancelling") or st.get("can_cancel") is False:
        return False
    step = st.get("step") or ""
    if step in ("", "lookup", "download", "check", "verify"):
        return True
    if step == "unpack":
        total = int(st.get("total") or 0)
        return not (total and int(st.get("done") or 0) >= total)
    return False


class ProgressNav:
    # ------------------------------------------------------------------------------------------ the jobs
    def _progress_name(self, gid):
        g = self.game_by_id(gid)
        if g is not None:
            return i18n.literal(g.short)
        from .game_releases import SOURCES
        return i18n.literal(SOURCES[gid].title if gid in SOURCES else gid)

    def progress_jobs(self):
        """The running installs/updates: dict(id, name, st, steps), games first, the launcher last."""
        jobs = []
        for gid, st in (getattr(self, "setup_state", None) or {}).items():
            if game_busy((st or {}).get("phase")):
                jobs.append(dict(id=gid, name=self._progress_name(gid), st=st, steps=STEP_TEXT))
        if launcher_busy((self.update_state or {}).get("phase")):
            jobs.append(dict(id=LAUNCHER, name="@progress.launcher", st=self.update_state, steps=UPDATE_STEP_TEXT))
        return jobs

    def update_running(self, g):
        """True while an install/update of this game runs: its Play / Build / Online say so and start nothing."""
        return g is not None and game_busy((self._setup(g.id) or {}).get("phase"))

    def progress_modal(self):
        return self.overlay == "dialog" and self.confirm_kind in ("setup_progress", "update_progress")

    def _progress_dialog_job(self):
        return LAUNCHER if self.confirm_kind == "update_progress" else getattr(self, "setup_game", "")

    def _progress_dialog_running(self):
        """-> (the job's state, whether it still runs)."""
        if self.confirm_kind == "update_progress":
            return self.update_state, launcher_dialog_busy(self.update_state.get("phase"))
        st = self._setup(getattr(self, "setup_game", ""))
        return st, game_busy(st.get("phase"))

    # ------------------------------------------------------------------------------------------ the dialog
    def _progress_dialog(self, a):
        """Buttons: 0 Hide (focused first), 1 Cancel -- there only while stopping is still safe."""
        st, running = self._progress_dialog_running()
        if not running:
            if a in ("back", "confirm"):
                self.overlay = None                     # the work is over: just close
            return
        count = 2 if cancel_safe(st) else 1
        if a in ("left", "right", "up", "down"):
            if count > 1:
                self.exit_focus = (self.exit_focus + 1) % count
            return
        if a not in ("back", "confirm"):
            return
        cancel = a == "confirm" and min(self.exit_focus, count - 1) == 1
        if not cancel:
            self.overlay = None
            self.say("@progress.hidden", 5)
        elif self.confirm_kind == "update_progress":
            if self.on_update_cancel is not None:
                self.on_update_cancel()
            self.say("@setup.cancelling")
        else:
            self.setup_cancelling = True
            self.on_setup("cancel", getattr(self, "setup_game", ""), None)
            self.say("@setup.cancelling")

    def _view_progress_dialog(self, v, title, text, st):
        cancellable = cancel_safe(st)
        installing = not cancellable and not st.get("cancelling")
        labels = ["@progress.hide"] + (["@cancel"] if cancellable else [])
        self.exit_focus = min(self.exit_focus, len(labels) - 1)
        v["dialog"] = dict(title="@progress.installing_title" if installing else title, text=text,
                           options=[dict(label=label, index=index, focused=self.exit_focus == index)
                                    for index, label in enumerate(labels)])
        v["hint"] = "@progress.hint_install" if installing else "@progress.hint"
        v["prompts"] = [self.prompt("confirm", labels[self.exit_focus])]
        if len(labels) > 1:
            v["prompts"].append(self.prompt("right", "@switch"))
        v["prompts"].append(self.prompt("back", "@progress.hide"))

    # ------------------------------------------------------------------------------------------ the card
    def _progress_line(self, name, st, steps):
        """"Tekken 4 · Download 45 % · 82/181 MB · 1 min": one running job."""
        if st.get("cancelling"):
            return i18n.message("progress.line_plain", name=name, text="@setup.cancelling")
        if st.get("phase") == "waiting":
            return i18n.message("progress.line_plain", name=name, text="@updates.waiting")
        if not cancel_safe(st):
            return i18n.message("progress.line_plain", name=name, text="@progress.installing")
        step = "@progress.step_download" if st.get("step") == "download" else steps.get(st.get("step"), steps.get("download"))
        total = int(st.get("total") or 0)
        if not total:
            return i18n.message("progress.line_plain", name=name, text=step)
        done = int(st.get("done") or 0)
        text = i18n.message("progress.line_mb", name=name, step=step, percent=min(100, int(done * 100 / total)),
                            done=self._mb(done), total=self._mb(total))
        left = int(st.get("left") or 0)
        if left:
            left_text = (i18n.message("progress.left_min", min=max(1, round(left / 60))) if left >= 60
                         else i18n.message("progress.left_s", sec=left))
            text = i18n.message("progress.line_left", text=text, left=left_text)
        return text

    def _progress_fraction(self, st):
        total = int(st.get("total") or 0)
        if not cancel_safe(st) or not total:
            return -1.0
        return max(0.0, min(1.0, int(st.get("done") or 0) / total))

    def progress_note_end(self, jid, name, kind, detail=None):
        """A job ended: done / cancelled stay on the card a few seconds, failed until it is opened."""
        self.progress_ends[jid] = dict(name=name, kind=kind, left=0.0 if kind == "failed" else END_SECONDS, detail=detail)

    def tick_progress(self, dt):
        changed = False
        for jid, end in list(self.progress_ends.items()):
            if end["kind"] == "failed":
                continue
            end["left"] -= dt
            if end["left"] <= 0:
                del self.progress_ends[jid]
                changed = True
        return changed

    def note_launcher_update(self):
        """Called with every launcher-update state: remember how a run ended, for the card."""
        phase = (self.update_state or {}).get("phase")
        running = launcher_busy(phase)
        if running:
            self.progress_ends.pop(LAUNCHER, None)
        elif self.progress_launcher_seen:
            kind = {"ready": "done", "cancelled": "cancelled"}.get(phase)
            if kind is None and phase not in ("idle", "current", "available"):
                kind = "failed"
            if kind:
                self.progress_note_end(LAUNCHER, "@progress.launcher", kind,
                                       self.update_failure_key() if kind == "failed" else None)
        self.progress_launcher_seen = running

    def progress_view(self):
        """The card: one line per running job (not the one whose dialog is open) and per job that just ended."""
        shown = self._progress_dialog_job() if self.progress_modal() else ""
        lines = [dict(id=j["id"], text=self._progress_line(j["name"], j["st"], j["steps"]),
                      fraction=self._progress_fraction(j["st"]), state="run")
                 for j in self.progress_jobs() if j["id"] != shown]
        running = {j["id"] for j in self.progress_jobs()}
        for jid, end in self.progress_ends.items():
            if jid in running:
                continue                                  # a new run of the same job: the running line says it
            lines.append(dict(id=jid, state=end["kind"], fraction=1.0 if end["kind"] == "done" else 0.0,
                              text=self._progress_end_text(end["kind"], end["name"])))
        return dict(show=bool(lines) and not self.overlay, lines=lines)

    @staticmethod
    def _progress_end_text(kind, name):
        if kind == "done":
            return i18n.message("progress.line_done", name=name)
        if kind == "cancelled":
            return i18n.message("progress.line_cancelled", name=name)
        return i18n.message("progress.line_failed", name=name)

    def progress_open(self, jid=""):
        """Selecting the card (or F7): a failed job's reason first, else the dialog of a running job."""
        if self.overlay:
            return False
        if jid in self.progress_ends:
            key = jid
        elif not jid:
            key = next((k for k, end in self.progress_ends.items() if end["kind"] == "failed"), None)
        else:
            key = None
        if key is not None:
            end = self.progress_ends.pop(key)
            if end["kind"] == "failed":
                self.say(end["detail"] or "@progress.failed_unknown", 12)
            return True
        jobs = self.progress_jobs()
        if not jobs:
            return False
        job = next((j for j in jobs if j["id"] == jid), None)
        if job is None:
            job = jobs[self.progress_next % len(jobs)]
            self.progress_next += 1
        if job["id"] == LAUNCHER:
            self._ask("update_progress")
        else:
            self.setup_game = job["id"]
            self._ask("setup_progress")
        return True

    # ------------------------------------------------------------------------------------------ "Update running"
    def lock_items(self, items):
        """Play / Build / Online of a game whose update runs: the actions say so and start nothing."""
        if not self.update_running(self.game):
            return items
        out = []
        for it in items:
            if it.get("kind") in ("action", "hold") and it.get("id") not in ("game_setup", "game_update"):
                it = dict(it, disabled=True, run=None, verb="", value="@progress.update_running",
                          hint="@progress.update_running")
            out.append(it)
        return out
