from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from run_session import Session, load_fixed_lines


class EndingTests(unittest.TestCase):
    def session(self, complete=False):
        session = Session.__new__(Session)
        session.ended = False
        session.workflow = SimpleNamespace(complete=complete)
        session.fixed = load_fixed_lines()
        session.inputs = Mock()
        session.nao = Mock()
        session.link = Mock()
        session.log = Mock()
        session._say_fixed = Mock()
        session.session_start = time.perf_counter()
        session.task_start = session.session_start
        session.turn = 2
        session.checks = 1
        return session

    def test_q_before_completion_uses_early_goodbye_by_default(self):
        session = self.session()
        session.end("experimenter", say_goodbye=config.SAY_GOODBYE_ON_EXPERIMENTER_END)
        session._say_fixed.assert_called_once_with("early_goodbye", session.fixed["early_goodbye"], config.GOODBYE_GESTURE)
        session.link.cleanup.assert_called_once()
        session.link.close.assert_called_once()
        session.log.close.assert_called_once()
        self.assertTrue(session.ended)

    def test_legacy_q_uses_early_goodbye_too(self):
        session = self.session()
        session.workflow = None
        session.end("experimenter")
        self.assertEqual(session._say_fixed.call_args.args[0], "early_goodbye")

    def test_completed_workflow_does_not_get_timeout_message(self):
        session = self.session(complete=True)
        session.end("workflow_complete", say_goodbye=False)
        session._say_fixed.assert_not_called()

    def test_duplicate_end_does_not_repeat_message(self):
        session = self.session()
        session.end("experimenter")
        session.end("experimenter")
        session._say_fixed.assert_called_once()
        session.log.close.assert_called_once()

    def test_playback_failure_still_logs_end_and_cleans_up(self):
        session = self.session()
        session._say_fixed.side_effect = RuntimeError("Audio unavailable")
        session.end("experimenter")
        self.assertIn("session_end", [call.args[0] for call in session.log.event.call_args_list])
        session.nao.restore_movement.assert_called_once()
        session.link.close.assert_called_once()
        session.log.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
