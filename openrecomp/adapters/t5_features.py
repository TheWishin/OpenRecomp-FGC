"""T5DR's optional installed-client features; snapshots never send requests."""
import importlib
import inspect


MODULES = (".t5_spectating", ".t5_tournaments", ".t5_profiles", ".t5_community",
           ".t5_accounts", ".t5_rules", ".t5_challenges")


def enabled(owner):
    return (owner.online_package == "t5lobby" and owner.online_lobby
            and owner.online_game != "t4")


def modules(owner):
    if enabled(owner):
        for name in MODULES:
            yield importlib.import_module(name, __package__) if isinstance(name, str) else name


def init(owner):
    for module in modules(owner):
        module.init(owner)


def state(owner, snapshot):
    for module in modules(owner):
        module.init(owner)
        extra = module.state(owner)
        snapshot["capabilities"].update(extra.get("capabilities") or {})
        snapshot.update({key: value for key, value in extra.items() if key != "capabilities"})
    return snapshot


def action(owner, action, client):
    return any(module.action(owner, action, client) for module in modules(owner))


def offline_action(owner, action):
    for module in modules(owner):
        handler = getattr(module, "offline_action", None)
        if handler and handler(owner, action):
            return True
    return False


def completion(owner, operation, value, error):
    return any(module.completion(owner, operation, value, error) for module in modules(owner))


def match_request(operation):
    return (operation in ("feature_challenges:send", "feature_challenges:cancel",
                          "feature_community:community_create", "feature_community:community_pair",
                          "feature_community:community_back_in_line", "feature_community:community_sit_out")
            or operation.startswith("feature_tour:accept:"))


def event(owner, event):
    handled = False
    for module in modules(owner):
        handled = bool(module.event(owner, event)) or handled
    return handled


def poll(owner):
    changed = False
    for module in modules(owner):
        handler = getattr(module, "poll", None)
        if handler:
            changed = bool(handler(owner)) or changed
    return changed


def close(owner):
    for module in modules(owner):
        handler = getattr(module, "close", None) or getattr(module, "reset", None)
        if handler:
            try:
                handler(owner)
            except Exception:  # a failed native viewer cleanup must not retain the lobby session
                pass


def options(owner, factory, base):
    """Old installations retain their constructor; optional flags need explicit support."""
    extra = {}
    if enabled(owner):
        extra["tournaments"] = True
        handler = getattr(owner, "_online_match_client_options", None)
        if handler:
            extra.update(handler())
        for module in modules(owner):
            handler = getattr(module, "client_options", None)
            if handler:
                extra.update(handler(owner))
    try:
        parameters = inspect.signature(factory).parameters
    except (ValueError, TypeError):
        return dict(base)
    accepts_extra = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters.values())
    return dict(base, **{key: value for key, value in extra.items()
                         if key not in base and (accepts_extra or key in parameters)})


def client_created(owner, client):
    for module in modules(owner):
        handler = getattr(module, "client_created", None)
        if handler:
            handler(owner, client)


def logged_in(owner, client):
    for module in modules(owner):
        handler = getattr(module, "logged_in", None)
        if handler:
            handler(owner, client)
