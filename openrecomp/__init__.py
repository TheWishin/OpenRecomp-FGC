"""OpenRecomp-FGC: Launcher for all your Recomps."""
__version__ = "0.1.8-dev"

from . import safety as _safety

_safety.enter_sandbox()          # no-op unless a test run (unittest/pytest/OPENRECOMP_TESTING=1) imports the package
