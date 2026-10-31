"""Game-library workers publish results on the backend thread, without a window."""
import queue
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp import app


class GenericBackendTests(unittest.TestCase):
    def test_worker_only_enqueues_preview_and_does_not_change_navigation(self):
        nav = SimpleNamespace(library_request=7, library_busy=False)
        backend = SimpleNamespace(nav=nav, _library_work=None, _library_results=queue.Queue(),
                                  _update_busy=lambda: False)
        operation = mock.Mock(return_value={"author": "Example"})
        with mock.patch.object(app.threading, "Thread") as thread:
            result = app.Backend._library_job(backend, "preview", operation)
            self.assertEqual(result, "@library.loading")
            operation.assert_not_called()
            self.assertTrue(nav.library_busy)
            thread.call_args.kwargs["target"]()
        self.assertEqual(backend._library_results.get_nowait(),
                         ("preview", 7, "", {"author": "Example"}, False))

    def test_worker_failure_is_bounded_catalog_feedback(self):
        nav = SimpleNamespace(library_request=2, library_busy=False)
        backend = SimpleNamespace(nav=nav, _library_work=None, _library_results=queue.Queue(),
                                  _update_busy=lambda: False)
        with mock.patch.object(app.threading, "Thread") as thread:
            app.Backend._library_job(backend, "check", mock.Mock(side_effect=OSError("private detail")), "example")
            thread.call_args.kwargs["target"]()
        self.assertEqual(backend._library_results.get_nowait(), ("check", 2, "example", None, True))

    def test_busy_worker_never_starts_a_second_operation(self):
        backend = SimpleNamespace(_library_work=("preview", 1, ""))
        with mock.patch.object(app.threading, "Thread") as thread:
            self.assertEqual(app.Backend._library_job(backend, "preview", mock.Mock()), "@library.busy")
        thread.assert_not_called()

    def test_poll_delivers_preview_with_original_request_and_clears_busy(self):
        nav = SimpleNamespace(library_busy=True, complete_game_preview=mock.Mock())
        backend = SimpleNamespace(nav=nav, _library_results=queue.Queue(), _library_work=("preview", 3, ""))
        preview = {"author": "Example"}
        backend._library_results.put(("preview", 3, "", preview, False))
        self.assertTrue(app.Backend._poll_library(backend))
        nav.complete_game_preview.assert_called_once_with(preview, request=3)
        self.assertFalse(nav.library_busy)
        self.assertIsNone(backend._library_work)

    def test_cancelled_check_never_publishes_an_offer(self):
        nav = SimpleNamespace(library_busy=True, library_request=4, complete_game_update=mock.Mock())
        backend = SimpleNamespace(nav=nav, _library_results=queue.Queue(), _library_work=("check", 3, "example"),
                                  _game_offers={})
        backend._library_results.put(("check", 3, "example", {"version": "v2.0.0"}, False))
        app.Backend._poll_library(backend)
        self.assertEqual(backend._game_offers, {})
        nav.complete_game_update.assert_not_called()

    def test_install_uses_the_same_service_that_checked_the_offer(self):
        game = SimpleNamespace(m={"adapter": "generic", "id": "example"})
        service = mock.Mock()
        service.install.return_value = "isolated-version"
        offer = {"version": "v2.0.0"}
        backend = SimpleNamespace(nav=SimpleNamespace(game_by_id=lambda game_id: game),
                                  config={"language": "de"}, _game_offers={"example": offer},
                                  _game_updaters={"example": service}, _library_work=None,
                                  _library_job=mock.Mock())
        app.Backend._install_game_update(backend, "example")
        operation = backend._library_job.call_args.args[1]
        self.assertEqual(operation(), dict(root="isolated-version", version="v2.0.0"))
        service.install.assert_called_once_with(game.m, offer)
        self.assertEqual(service.config, backend.config)
        self.assertIsNot(service.config, backend.config)


if __name__ == "__main__":
    unittest.main()
