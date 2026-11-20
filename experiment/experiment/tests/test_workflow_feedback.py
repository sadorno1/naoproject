import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow_feedback import generate_feedback


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.client.chat.completions.create.return_value.choices = [Mock(message=Mock(
            content=json.dumps({"speech": "Great work!"})))]
        self.step = dict(title="Build 1", instruction="Place the red block.", expected="One red block.",
                         hint="Check the red block's position.")

    def test_wrong_result_includes_mismatch_and_authored_hint(self):
        self.assertEqual(generate_feedback(self.client, self.step, "retry", "Red block is offset."), "Great work!")
        messages = self.client.chat.completions.create.call_args.kwargs["messages"]
        data = json.loads(messages[1]["content"])
        self.assertEqual(data["observed_mismatch"], "Red block is offset.")
        self.assertEqual(data["authored_hint"], self.step["hint"])
        self.assertIn("exact instruction will be spoken separately", messages[0]["content"])

    def test_completion_prompt_celebrates_and_names_next_activity(self):
        generate_feedback(self.client, self.step, "activity_complete", next_title="Build 2")
        messages = self.client.chat.completions.create.call_args.kwargs["messages"]
        self.assertIn("Celebrate completing this entire activity", messages[0]["content"])
        self.assertEqual(json.loads(messages[1]["content"])["next_activity"], "the next build")

    def test_praise_is_short_and_internal_labels_are_rejected(self):
        for speech in ("You did a really very great job!", "Great, Step 5!", "Build 1 is done!"):
            self.client.chat.completions.create.return_value.choices[0].message.content = json.dumps({"speech": speech})
            with self.assertRaises(ValueError):
                generate_feedback(self.client, self.step, "step_correct")

    def test_final_celebration_does_not_invite_nonexistent_build(self):
        generate_feedback(self.client, self.step, "session_complete")
        prompt = self.client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertIn("Do not suggest another build", prompt)

    def test_empty_or_oversized_feedback_is_rejected(self):
        for speech in ("", "word " * 56):
            self.client.chat.completions.create.return_value.choices[0].message.content = json.dumps({"speech": speech})
            with self.assertRaises(ValueError):
                generate_feedback(self.client, self.step, "step_correct")


if __name__ == "__main__":
    unittest.main()
