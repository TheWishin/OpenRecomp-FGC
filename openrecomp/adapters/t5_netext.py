"""T5DR 1.2.1 online preferences and account removal through the installed client."""
import inspect
import os
import re

from .t5_coexist import readonly_imports
from .. import i18n


FEELS = ("responsive", "balanced", "smooth")
PINGS = (None, 60, 100, 150)


def init(owner):
    if hasattr(owner, "_netext_preferences"):
        return
    cfg = owner._online_config()
    feel = cfg.get("online_feel", owner.s.get("online_feel"))
    owner._netext_preferences = dict(max_ping=cfg.get("max_ping") if cfg.get("max_ping") in PINGS else None,
        no_wifi=cfg.get("no_wifi") is True, steady=cfg.get("steady") is True,
        online_feel=feel if feel in FEELS else "balanced",
        net_line=cfg.get("net_line", owner.s.get("net_line")) is True)
    owner._netext_forget = None
    owner._netext_removing = False


def feature(client, name):
    welcome = getattr(client, "welcome", None)
    features = welcome.get("features") if isinstance(welcome, dict) else None
    return isinstance(features, (list, tuple)) and name in features


def filters(owner, client):
    if not feature(client, "mm_filters"):
        return False
    # Old installed clients must keep their original queue signature even on a new server.
    try:
        return all("options" in inspect.signature(getattr(client, method)).parameters
                   for method in ("quick_match", "ranked_match"))
    except (AttributeError, TypeError, ValueError):
        return False


def options(owner, client):
    if not filters(owner, client):
        return {}
    init(owner)
    return dict(options={key: owner._netext_preferences[key] for key in ("max_ping", "no_wifi", "steady")})


def state(owner):
    init(owner)
    client = owner._online_client
    return dict(capabilities=dict(search_options=filters(owner, client), online_feel=True,
        forget_me=bool(owner._online_account and feature(client, "forget_me")
                       and callable(getattr(client, "forget_me", None)))),
        netext=dict(owner._netext_preferences), netext_session=owner._online_generation,
        forget_counts=dict(owner._netext_forget[3]) if owner._netext_forget else None)


def tags(row):
    out = {}
    if row.get("area") in ("na", "sa", "eu", "af", "as", "oc"):
        out["area"] = row["area"]
    lang = row.get("lang")
    if isinstance(lang, str) and re.fullmatch(r"[a-z]{2,3}(?:-[A-Z]{2})?", lang):
        out["lang"] = lang
    return out


def launch_env(owner):
    owner._online_init()
    init(owner)
    prefs = owner._netext_preferences
    return dict(T5_RB_NET_FEEL=prefs["online_feel"], T5_NET_LINE="1" if prefs["net_line"] else "0",
                T5_RB_COST_FILE=os.path.join(owner._online_out_dir(), "rb_cost.txt"))


def action(owner, operation, client):
    if not operation.startswith("netext_"):
        return False
    init(owner)
    if operation == "netext_forget_cancel":
        owner._netext_forget = None
        owner._online_fields["online_current_password"] = ""
        return True
    if owner._online_phase != "logged_in" or owner._online_busy:
        return True
    caps = state(owner)["capabilities"]
    key = operation.removeprefix("netext_")
    selected = None
    if operation.startswith("netext_set:"):
        parts = operation.split(":", 2)
        if len(parts) != 3:
            return True
        _prefix, key, selected = parts
    if key in owner._netext_preferences:
        if key in ("max_ping", "no_wifi", "steady") and not caps["search_options"]:
            return True
        prefs = dict(owner._netext_preferences)
        choices = PINGS if key == "max_ping" else FEELS if key == "online_feel" else (False, True)
        if selected is not None:
            matches = [value for value in choices if ("any" if value is None else str(value).lower()) == selected]
            if not matches:
                return True
            prefs[key] = matches[0]
        elif key == "max_ping":
            prefs[key] = PINGS[(PINGS.index(prefs[key]) + 1) % len(PINGS)]
        elif key == "online_feel":
            prefs[key] = FEELS[(FEELS.index(prefs[key]) + 1) % len(FEELS)]
        else:
            prefs[key] = not prefs[key]
        try:
            owner._online_write_preferences({key: prefs[key]})
            owner._netext_preferences = prefs
        except (OSError, ValueError, TypeError):
            owner._online_message = "@online.save_failed"
        return True
    if operation not in ("netext_forget_preview", "netext_forget_confirm") or not caps["forget_me"]:
        return True
    generation = owner._online_generation
    if operation == "netext_forget_preview":
        password = owner._online_fields["online_current_password"]
        owner._online_fields["online_current_password"] = ""
        owner._netext_forget = None
        if not password:
            owner._online_message = "@online.password_required"
            return True
    else:
        proof, owner._netext_forget = owner._netext_forget, None
        if not proof or proof[:2] != (client, generation):
            return True
        password = proof[2]
        owner._netext_removing = True
    preview = operation == "netext_forget_preview"

    def work():
        owner._online_check_request(generation, client)
        if owner._online_phase != "logged_in" or not state(owner)["capabilities"]["forget_me"]:
            raise RuntimeError("@online.cancelled")
        if preview:
            reply = client.forget_me(password, True)
            counts = reply.get("counts") if isinstance(reply, dict) else None
            if not isinstance(counts, dict):
                raise RuntimeError("@online.failure")
            return (client, generation, password,
                    {key: min(n, 10 ** 9) if isinstance(n, int) and not isinstance(n, bool) and n >= 0 else 0
                     for key in ("matches", "sets", "friends") for n in (counts.get(key, 0),)})
        previous = getattr(client, "session", None)
        saved = owner._online_saved()
        remembered = saved.get("token") if saved and saved.get("name") == owner._online_name else previous
        client.forget_me(password)
        with owner._online_lock:
            owner._online_check_request(generation, client)
            warning = ""
            try:
                owner._online_write_session(owner._online_fields["online_server"], None, None, expected=remembered)
            except (OSError, ValueError, TypeError):
                warning = "@online.save_failed"
            # Also reject a token borrowed from the native launcher without changing its file.
            rejected = getattr(owner, "_online_rejected_sessions", {})
            server = owner._online_fields["online_server"].strip().lower()
            rejected[server] = remembered
            owner._online_rejected_sessions = rejected
            return warning

    owner._online_submit("feature_" + operation, work)
    return True


def completion(owner, operation, value, error):
    if not operation.startswith("feature_netext_"):
        return False
    owner._netext_removing = False
    if error:
        owner._netext_forget = None
        owner._online_message = owner._online_error(error)
    elif operation == "feature_netext_forget_preview":
        owner._netext_forget = value
        owner._online_message = "@netext.forget_review"
    else:
        owner.online_close()
        owner._online_auto_tried = True
        owner._online_message = value or "@netext.forgotten"
    return True


def logged_in(owner, client):
    if not feature(client, "mm_filters") or not callable(getattr(client, "send_netinfo", None)):
        return
    # Optional metadata must not turn a successful login into a failure on an older installation.
    wifi = None
    try:
        import importlib
        with readonly_imports():
            module = importlib.import_module(owner.online_package + ".netinfo")
        wifi = module.on_wifi()
    except Exception:
        pass
    try:
        client.send_netinfo(wifi=wifi if isinstance(wifi, bool) else None, area="auto",
                            lang=i18n.normalize(owner.config.get("language")))
    except Exception:
        pass


def event(owner, event):
    return False


def reset(owner):
    init(owner)
    owner._netext_forget = None
    owner._netext_removing = False
