"""The common adapter hides native tools unless the game provides them."""
import unittest

from openrecomp.adapters.base import Adapter
from openrecomp.adapters.t5dr import T5DR
from openrecomp.adapters.t5_controls import Controls
from openrecomp.adapters.support import T5Support


class OptionalTools(unittest.TestCase):
    def test_base_adapter_has_safe_optional_tools(self):
        adapter = Adapter(dict(id="fake", short="Fake"))
        self.assertFalse(adapter.controls_supported())
        self.assertEqual(adapter.controls(), [])
        self.assertFalse(adapter.support_available())
        self.assertEqual(adapter.support_state(), dict(
            running=False, operation="", checked=False, findings=[], report="", error=""))
        with self.assertRaises(RuntimeError):
            adapter.begin_binding("pad", "1")
        with self.assertRaises(RuntimeError):
            adapter.support_start("report")
        adapter.cancel_binding()
        adapter.controls_close()

    def test_t5dr_uses_the_runtime_tools_instead_of_empty_base_methods(self):
        self.assertIs(T5DR.controls, Controls.controls)
        self.assertIs(T5DR.begin_binding, Controls.begin_binding)
        self.assertIs(T5DR.support_start, T5Support.support_start)
        self.assertIs(T5DR.support_state, T5Support.support_state)


if __name__ == "__main__":
    unittest.main()
