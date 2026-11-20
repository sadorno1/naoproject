import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from build_workflow import ACTIVITIES, BuildWorkflow
from reference_capture import HeadCaptureTrigger, save_reference
from run_session import Session
from step_vision import compare_step


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        out = io.BytesIO()
        Image.new("RGB", (16, 16), "red").save(out, "JPEG")
        self.jpeg = out.getvalue()
        for activity in ACTIVITIES:
            folder = self.root / activity
            write(folder / "build.json", {"title": activity, "start_instruction": "Clear the area.",
                                         "steps": ["step_01", "step_02"]})
            for number in (1, 2):
                step = folder / f"step_{number:02d}"
                write(step / "step.json", {"instruction": f"Place block {number}.",
                                          "expected": f"{number} blocks visible.", "ready": True,
                                          "reference_photo": "reference.jpg"})
                (step / "reference.jpg").write_bytes(self.jpeg)

    def test_tutorial_and_three_builds_advance_only_on_yes(self):
        flow = BuildWorkflow(self.root)
        self.assertEqual([s["activity"] for s in flow.steps], [a for a in ACTIVITIES for _ in range(2)])
        flow.advance("no")
        flow.advance("uncertain")
        self.assertEqual(flow.index, 0)
        for _ in range(7):
            self.assertFalse(flow.advance("yes"))
        self.assertTrue(flow.advance("yes"))
        self.assertTrue(flow.complete)

    def test_rehearsal_selects_only_one_build(self):
        flow = BuildWorkflow(self.root, only="build_2")
        self.assertEqual(len(flow.steps), 2)
        self.assertEqual(flow.current["activity"], "build_2")

    def test_draft_is_rejected_before_running(self):
        path = self.root / "tutorial/step_01/step.json"
        data = json.loads(path.read_text())
        data["ready"] = False
        write(path, data)
        with self.assertRaisesRegex(ValueError, "ready=true"):
            BuildWorkflow(self.root)

    def test_missing_photo_and_blank_description_are_rejected(self):
        path = self.root / "tutorial/step_01/step.json"
        data = json.loads(path.read_text())
        data["expected"] = ""
        write(path, data)
        with self.assertRaisesRegex(ValueError, "expected"):
            BuildWorkflow(self.root)
        data["expected"] = "One red block."
        write(path, data)
        (path.parent / "reference.jpg").unlink()
        with self.assertRaises(FileNotFoundError):
            BuildWorkflow(self.root)

    def test_reference_outside_step_folder_is_rejected(self):
        path = self.root / "tutorial/step_01/step.json"
        data = json.loads(path.read_text())
        data["reference_photo"] = "../../outside.jpg"
        write(path, data)
        with self.assertRaisesRegex(ValueError, "escapes"):
            BuildWorkflow(self.root)

    def test_changed_camera_settings_require_reference_review(self):
        write(self.root / "tutorial/step_01/capture.json", {"camera_index": -1})
        with self.assertRaisesRegex(ValueError, "camera_index differs"):
            BuildWorkflow(self.root)

    def test_next_activity_starts_with_reset_instruction(self):
        flow = BuildWorkflow(self.root)
        flow.advance("yes")
        self.assertNotIn("Clear the area", flow.announcement())
        flow.advance("yes")
        self.assertEqual(flow.current["activity"], "build_1")
        self.assertIn("Clear the area", flow.announcement())

    def test_capture_never_overwrites_and_new_step_requires_review(self):
        with self.assertRaises(FileExistsError):
            save_reference(self.root, "tutorial", 1, self.jpeg, {})
        path = save_reference(self.root, "tutorial", 3, self.jpeg, {})
        self.assertEqual(path.read_bytes(), self.jpeg)
        self.assertFalse(json.loads((path.parent / "step.json").read_text())["ready"])
        spec = json.loads((self.root / "tutorial/build.json").read_text())
        self.assertEqual(spec["steps"][-1], "step_03")

    def session(self):
        session = Session.__new__(Session)
        session.workflow = BuildWorkflow(self.root)
        session.checks = 0
        session.dry_run = True
        session.nao = Mock()
        session.client = Mock()
        session.log = Mock()
        session.log.image_path.return_value = str(self.root / "live.jpg")
        session.inputs = Mock()
        session.vision = Mock()
        session.vision.preprocess_image.return_value = self.jpeg
        session._capture = Mock(return_value="dry_run_file")
        session._say_fixed = Mock()
        session._announce_step = Mock()
        session._say_workflow_feedback = Mock()
        session.end = Mock()
        session.fixed = {"look": ["Checking."]}
        return session

    def test_yes_speaks_confirmation_and_next_instruction(self):
        session = self.session()
        with patch("step_vision.compare_step", return_value=({"verdict": "yes", "reason": "Matches."}, {})):
            session._check(1.0, "LeftBumperPressed")
        self.assertEqual(session.workflow.index, 1)
        session._say_workflow_feedback.assert_called_once_with(session.workflow.steps[0], "step_correct")
        session._announce_step.assert_called_once()
        session.end.assert_not_called()

    def test_no_and_uncertain_do_not_advance(self):
        for verdict in ("no", "uncertain"):
            session = self.session()
            with patch("step_vision.compare_step", return_value=({"verdict": verdict, "reason": "Not verified."}, {})):
                session._check(1.0, "LeftBumperPressed")
            self.assertEqual(session.workflow.index, 0)
            session._announce_step.assert_not_called()
            session.end.assert_not_called()
            if verdict == "no":
                session._say_workflow_feedback.assert_called_once_with(
                    session.workflow.current, "retry", reason="Not verified.")
                instruction = session._say_fixed.call_args_list[-1].args[1]
                self.assertIn("Place block 1.", instruction)
                self.assertNotIn("Clear the area", instruction)
            else:
                session._say_workflow_feedback.assert_not_called()

    def test_activity_end_celebrates_before_announcing_next_build(self):
        session = self.session()
        session.workflow.index = 1
        events = []
        session._say_workflow_feedback.side_effect = lambda *a, **kw: events.append(("feedback", a, kw))
        session._announce_step.side_effect = lambda: events.append(("announce",))
        with patch("step_vision.compare_step", return_value=({"verdict": "yes", "reason": "Matches."}, {})):
            session._check(1.0, "LeftBumperPressed")
        self.assertEqual(events[0][1][1], "activity_complete")
        self.assertEqual(events[0][2]["next_title"], "build_1")
        self.assertEqual(events[1], ("announce",))
        self.assertEqual(session.workflow.current["activity"], "build_1")

    def test_feedback_api_failure_uses_fallback(self):
        session = self.session()
        with patch("workflow_feedback.generate_feedback", side_effect=RuntimeError("Offline")):
            Session._say_workflow_feedback(session, session.workflow.current, "step_correct")
        session._say_fixed.assert_called_once_with("workflow_step_correct", "That's correct, nice work! Let's move on to the next step.")

    def test_generated_feedback_is_spoken_as_returned(self):
        session = self.session()
        with patch("workflow_feedback.generate_feedback", return_value="You got it! Great building."):
            Session._say_workflow_feedback(session, session.workflow.current, "step_correct")
        session._say_fixed.assert_called_once_with("workflow_step_correct", "You got it! Great building.")

    def test_api_failure_does_not_advance(self):
        session = self.session()
        with patch("step_vision.compare_step", side_effect=RuntimeError("Offline")):
            session._check(1.0, "LeftBumperPressed")
        self.assertEqual(session.workflow.index, 0)
        session._say_fixed.assert_any_call("check_failed", "I couldn't check that photo. Please clear the view and press my left foot bumper to try again.")

    def test_changed_reference_does_not_call_model_or_advance(self):
        session = self.session()
        Path(session.workflow.current["reference_photo"]).write_bytes(b"changed")
        with patch("step_vision.compare_step") as compare:
            session._check(1.0, "LeftBumperPressed")
        compare.assert_not_called()
        self.assertEqual(session.workflow.index, 0)

    def test_final_yes_ends_only_after_all_steps(self):
        session = self.session()
        session.workflow.index = len(session.workflow.steps) - 1
        with patch("step_vision.compare_step", return_value=({"verdict": "yes", "reason": "Matches."}, {})):
            session._check(1.0, "LeftBumperPressed")
        session.end.assert_called_once_with("workflow_complete", say_goodbye=False)
        session._announce_step.assert_not_called()
        session._say_workflow_feedback.assert_called_once_with(session.workflow.steps[-1], "session_complete")


class CaptureTriggerTests(unittest.TestCase):
    def test_touch_started_during_capture_is_not_queued_after_it_finishes(self):
        trigger = HeadCaptureTrigger()
        trigger.touch(1, 0)
        trigger.touch(0, 0.1)
        trigger.requests.get_nowait()
        trigger.touch(1, 1)
        trigger.finish()
        trigger.touch(0, 2)
        self.assertTrue(trigger.requests.empty())

    def test_hold_release_debounce_and_busy_do_not_duplicate_photos(self):
        trigger = HeadCaptureTrigger()
        trigger.touch(1, 0)
        trigger.touch(1, 0.1)
        self.assertTrue(trigger.requests.empty())
        trigger.touch(0, 0.2)
        self.assertEqual(trigger.requests.qsize(), 1)
        trigger.touch(1, 1)
        trigger.touch(0, 1.2)
        self.assertEqual(trigger.requests.qsize(), 1)  #busy
        trigger.requests.get_nowait()
        trigger.finish()
        trigger.touch(0, 1.3)
        self.assertTrue(trigger.requests.empty())
        trigger.touch(1, 2)
        trigger.touch(0, 2.1)
        self.assertEqual(trigger.requests.qsize(), 1)


class ComparisonTests(unittest.TestCase):
    def test_reference_precedes_live_and_verdict_is_parsed(self):
        client = Mock()
        client.chat.completions.create.return_value.choices = [Mock(message=Mock(
            content=json.dumps({"verdict": "yes", "reason": "Same blocks and arrangement."})))]
        result, _ = compare_step(client, b"live", b"reference", "One red block.", retries=0)
        self.assertEqual(result["verdict"], "yes")
        content = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        self.assertIn("One red block.", content[0]["text"])
        self.assertIn("cmVmZXJlbmNl", content[1]["image_url"]["url"])
        self.assertIn("bGl2ZQ==", content[3]["image_url"]["url"])

    def test_invalid_verdict_fails_instead_of_passing(self):
        client = Mock()
        client.chat.completions.create.return_value.choices = [Mock(message=Mock(
            content=json.dumps({"verdict": "maybe", "reason": "Unsure."})))]
        with self.assertRaises(RuntimeError):
            compare_step(client, b"live", b"reference", "One red block.", retries=0)


if __name__ == "__main__":
    unittest.main()
