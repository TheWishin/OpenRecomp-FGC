"""Retain the selected T5 Python when an installed legacy start() uses sys.executable."""
from types import FunctionType


class _BuildSys:
    def __init__(self, original, executable):
        self._original = original
        self.executable = executable

    def __getattr__(self, name):
        return getattr(self._original, name)


def start_build_with_python(run, executable):
    # T5DR 1.2.0 start() changes cmd[0] to its parent pythonw.exe's sibling Python,
    # undoing our selection. A private sys view preserves the installed method's
    # warmup, environment, process flags and event pump without changing shared sys.
    start = getattr(run.start, "__func__", None)
    if not isinstance(start, FunctionType) or "sys" not in start.__globals__:
        raise RuntimeError("@t5.install_incomplete_tools")
    run.cmd[0] = executable
    scope = dict(start.__globals__)
    scope["sys"] = _BuildSys(scope["sys"], executable)
    selected_start = FunctionType(start.__code__, scope, start.__name__,
                                  start.__defaults__, start.__closure__)
    selected_start.__kwdefaults__ = start.__kwdefaults__
    return selected_start(run)
