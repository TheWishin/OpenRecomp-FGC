"""Makes the adapter a manifest names. A game whose folder or core cannot be used becomes a Missing with the reason."""
import importlib.util

from .base import Generic, Missing


def _has_code(kind):
    """A code adapter this launcher has (make() below knows it and its module is here)."""
    return kind in KNOWN and importlib.util.find_spec(f"{__name__}.{kind}") is not None


KNOWN = ("t5dr", "t4", "tag2")          # make() handles these kinds; a branch that adds an adapter adds its kind here


def make(manifest, config):
    kind = manifest["adapter"]
    if kind == "generic":
        return Generic(manifest, config)
    if kind == "broken":
        from .manifest_game import Broken
        return Broken(manifest, config)
    if kind == "manifest":
        # A bundled manifest may hand the game to launcher code that does what data cannot (code_adapter); while
        # that code is not part of this launcher, the manifest alone is the game.
        code = manifest.get("code_adapter") if manifest.get("builtin") else None
        if code and _has_code(code):
            return make(dict(manifest, adapter=code), config)
        from .manifest_game import ManifestGame
        try:
            return ManifestGame(manifest, config)
        except Exception as e:  # noqa: BLE001 -- one broken game must not take the launcher down
            missing = Missing(manifest, config)
            missing.problem = f"{manifest['short']}: {e}"
            return missing
    try:
        if kind == "t5dr":
            from .t5dr import T5DR, LegacyT5DR, find_root, legacy_install
            root = find_root(manifest, config)
            if root:
                if legacy_install(root):
                    return LegacyT5DR(manifest, config, root)
                return T5DR(manifest, config, root)
        elif kind == "t4":
            from .t4 import T4, configured_problem, find_root
            root = find_root(manifest, config)
            if root:
                return T4(manifest, config, root)
            wrong = configured_problem(manifest, config)
            if wrong:
                missing = Missing(manifest, config)
                missing.wrong_folder = wrong
                return missing
        elif kind == "tag2":
            from .tag2 import Tag2
            return Tag2(manifest, config)
    except Exception as e:  # noqa: BLE001 -- one broken game must not take the launcher down
        missing = Missing(manifest, config)
        missing.problem = f"{manifest['short']}: {e}"
        return missing
    return Missing(manifest, config)
