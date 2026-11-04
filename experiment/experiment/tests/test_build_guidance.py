"""Offline regression tests: python -m unittest discover -s tests -v."""
import io
import sys
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
import vision
from nao_proxy import NaoProxy, photo_result_path
from run_session import Session


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.target = vision.load_target()
        self.obs = {"scene_clear": True, "notes": "", "blocks": [
            {**{k: v for k, v in b.items() if k not in ("id", "front_visible")}, "visibility": "visible"}
            for b in self.target["blocks"]]}

    def test_pillar_uses_exact_inventory(self):
        self.assertEqual(Counter((b["color"], b["type"]) for b in self.target["blocks"]),
                         {("light_blue", "2x2"): 2, ("red", "1x2"): 4, ("blue", "1x4"): 2})
        self.assertEqual({b["layer"] for b in self.target["blocks"]}, set(range(5)))

    def test_correct_pillar(self):
        self.assertEqual(vision.validate_observation(self.obs), [])
        self.assertTrue(vision.compare_build(self.obs, self.target)["match"])

    def test_whole_build_translation(self):
        for b in self.obs["blocks"]:
            b["x"] += 7
            b["y"] -= 3
        self.assertTrue(vision.compare_build(self.obs, self.target)["match"])

    def test_missing_piece(self):
        self.obs["blocks"].pop()
        diff = vision.compare_build(self.obs, self.target)
        self.assertFalse(diff["match"])
        self.assertEqual(diff["missing"], ["red_top_back"])

    def test_light_blue_is_distinct(self):
        self.obs["blocks"][0]["color"] = "blue"
        self.assertFalse(vision.compare_build(self.obs, self.target)["match"])

    def test_rotated_long_piece(self):
        self.obs["blocks"][1]["orientation"] = 90
        diff = vision.compare_build(self.obs, self.target)
        self.assertFalse(diff["match"])
        self.assertTrue(diff["wrong"][0]["issues"]["rotate"])

    def test_empty_frame_is_not_missing_blocks_instruction(self):
        self.obs["blocks"] = []
        diff = vision.compare_build(self.obs, self.target)
        self.assertFalse(diff["match"])
        self.assertIn("cannot be assessed", vision.describe_diff(diff))
        self.assertNotIn("Not placed yet", vision.describe_diff(diff))

    def test_unclear_frame_cannot_complete_even_with_matching_blocks(self):
        self.obs["scene_clear"] = False
        diff = vision.compare_build(self.obs, self.target)
        self.assertFalse(diff["match"])
        self.assertNotIn("Needs fixing", vision.describe_diff(diff))

    def test_unknown_extra_cannot_complete(self):
        self.obs["blocks"].append(dict(color="unknown", type="unknown", orientation=None,
                                        x=None, y=None, layer=0, visibility="not_visible"))
        diff = vision.compare_build(self.obs, self.target)
        self.assertFalse(diff["match"])
        self.assertEqual(diff["unverifiable_count"], 1)

    def test_hidden_piece_does_not_trigger_missing_instruction(self):
        self.obs["blocks"][0].update(color="unknown", x=None, visibility="not_visible")
        text = vision.describe_diff(vision.compare_build(self.obs, self.target))
        self.assertNotIn("Not placed yet", text)
        self.assertIn("clearer view", text)

    def test_malformed_observation_is_rejected(self):
        self.obs["blocks"] = [None]
        self.assertTrue(vision.validate_observation(self.obs))
        self.obs["blocks"] = [dict(self.target["blocks"][0], x=1.5, visibility="visible")]
        self.assertTrue(vision.validate_observation(self.obs))

    def test_preprocessing_retains_camera_detail(self):
        from PIL import Image
        image = Image.new("RGB", (1280, 960), "lightblue")
        jpeg = vision.preprocess_image(image)
        self.assertEqual(Image.open(io.BytesIO(jpeg)).size, (1280, 960))


class MotionTests(unittest.TestCase):
    def setUp(self):
        self.nao = NaoProxy(None)
        self.nao.animate = Mock()
        self.nao.animate.isBehaviorInstalled.return_value = True
        self.nao.animate.getRunningBehaviors.return_value = []

    def test_gestures_disabled_by_default(self):
        self.assertEqual(self.nao.change_expression("excited")[1], "disabled")
        self.nao.animate.startBehavior.assert_not_called()

    def test_gestures_never_overlap(self):
        with patch.object(config, "GESTURES_ENABLED", True), patch.object(config, "GESTURE_COOLDOWN_S", 0):
            path, status = self.nao.change_expression("nod")
            self.assertEqual(status, "started")
            self.nao.animate.getRunningBehaviors.return_value = [path]
            self.assertEqual(self.nao.change_expression("happy")[1], "busy")
            self.assertEqual(self.nao.animate.startBehavior.call_count, 1)

    def test_gesture_cooldown(self):
        with patch.object(config, "GESTURES_ENABLED", True):
            self.nao.change_expression("nod")
            self.assertEqual(self.nao.change_expression("happy")[1], "cooldown")

    def test_head_movement_blocks_and_settles(self):
        self.nao.motion = Mock()
        with patch("nao_proxy.time.sleep") as sleep:
            self.nao.set_head_pose()
            self.nao.motion.angleInterpolationWithSpeed.assert_called_once_with(
                ["HeadYaw", "HeadPitch"], [config.HEAD_YAW, config.HEAD_PITCH], config.HEAD_SPEED)
            self.nao.motion.setAngles.assert_not_called()
            sleep.assert_called_once_with(config.HEAD_SETTLE_S)

    def test_background_movement_is_restored(self):
        self.nao.awareness = Mock()
        self.nao.awareness.isAwarenessRunning.return_value = True
        self.nao.autonomous_moves = Mock()
        self.nao.autonomous_moves.getBackgroundStrategy.return_value = "backToNeutral"
        self.nao.autonomous_moves.getExpressiveListeningEnabled.return_value = True
        self.nao.quiet_movement()
        self.nao.awareness.stopAwareness.assert_called_once()
        self.nao.autonomous_moves.setBackgroundStrategy.assert_called_with("none")
        self.nao.restore_movement()
        self.nao.awareness.startAwareness.assert_called_once()
        self.nao.autonomous_moves.setBackgroundStrategy.assert_called_with("backToNeutral")
        self.nao.autonomous_moves.setExpressiveListeningEnabled.assert_called_with(True)

    def test_photo_paths(self):
        for result in (["/home/nao", "check.jpg"], ["/home/nao/check.jpg"], "/home/nao/check.jpg"):
            self.assertEqual(photo_result_path(result, "/home/nao", "check"), "/home/nao/check.jpg")


class CameraCheckTests(unittest.TestCase):
    def make_session(self):
        session = Session.__new__(Session)
        session.checks = 0
        session.turn = 0
        session.fixed = {"look": ["Let me check."]}
        session.inputs = Mock()
        session.log = Mock()
        session.nao = Mock()
        session.dry_run = False
        session._say_fixed = Mock()
        session._respond = Mock()
        session._capture = Mock(side_effect=RuntimeError("stop test after pose"))
        return session

    def test_head_is_restored_with_no_look_gesture(self):
        session = self.make_session()
        session.nao.wait_for_gestures.return_value = True
        with patch.object(config, "LOOK_GESTURE", None):
            session._check(0, "bumper")
        session.nao.set_head_pose.assert_called_once_with(wait=True)
        session._capture.assert_called_once()

    def test_moving_robot_is_not_photographed(self):
        session = self.make_session()
        session.nao.wait_for_gestures.return_value = False
        session._check(0, "bumper")
        session.nao.stop_gestures.assert_called_once()
        session._capture.assert_not_called()
        session._respond.assert_called_once()


if __name__ == "__main__":
    unittest.main()
