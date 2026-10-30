"""Makes the adapter a manifest names. A game whose folder or core cannot be used becomes a Missing with the reason."""
from .base import Generic, Missing


def make(manifest, config):
    kind = manifest["adapter"]
    if kind == "generic":
        return Generic(manifest, config)
    try:
        if kind == "t5dr":
            from .t5dr import T5DR, find_root
            root = find_root(manifest, config)
            if root:
                return T5DR(manifest, config, root)
        elif kind == "t4":
            from .t4 import T4, find_root
            root = find_root(manifest, config)
            if root:
                return T4(manifest, config, root)
    except Exception as e:  # noqa: BLE001 -- one broken game must not take the launcher down
        missing = Missing(manifest, config)
        missing.problem = f"{manifest['short']}: {e}"
        return missing
    return Missing(manifest, config)
