"""Clipboard requests stay plain data until the app handles an explicit action."""
import unittest

from openrecomp.nav import Nav


class BundleClipboard(unittest.TestCase):
    def test_explicit_copy_requests_exact_command(self):
        nav = Nav([])
        self.assertIsNone(nav.pending_clipboard)
        command = 'winget install --id Python.Python.3.12 --exact'
        nav.copy_text(command)
        self.assertEqual(nav.pending_clipboard, command)

    def test_dry_copy_has_no_clipboard_effect(self):
        nav = Nav([])
        nav.dry = True
        nav.copy_text('winget install --id Git.Git --exact')
        self.assertIsNone(nav.pending_clipboard)
        self.assertTrue(nav.toast)
