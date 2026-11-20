import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from photo_mode import PhotoBatch, run_photo_mode
from run_session import main, parse_args


class PhotoModeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        out = io.BytesIO()
        Image.new("RGB", (20, 20), "red").save(out, "JPEG")
        self.jpeg = out.getvalue()

    def test_photo_flag_needs_no_participant_or_condition(self):
        args = parse_args(["--photo-mode", "--ip", "robot"])
        self.assertTrue(args.photo_mode)
        self.assertIsNone(args.pid)
        self.assertIsNone(args.condition)

    def test_normal_sessions_still_require_participant_and_condition(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_args(["--ip", "robot"])

    def test_photo_mode_requires_robot_and_rejects_session_flags(self):
        for args in (["--photo-mode"], ["--photo-mode", "--ip", "robot", "--dry-run"],
                     ["--photo-mode", "--ip", "robot", "--activity", "tutorial"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args(args)

    def test_photo_dispatch_bypasses_participant_session(self):
        with patch("photo_mode.run_photo_mode", return_value=0) as run, patch("run_session.Session") as session:
            self.assertEqual(main(["--photo-mode", "--ip", "robot", "--photo-dir", str(self.root)]), 0)
        session.assert_not_called()
        run.assert_called_once_with("robot", str(self.root))

    def test_zip_includes_only_numbered_photos_and_metadata(self):
        batch = PhotoBatch(self.root)
        self.assertEqual(batch.save(self.jpeg, "photo").name, "photo_001.jpg")
        self.assertEqual(batch.save(self.jpeg, "video").name, "photo_002.jpg")
        (batch.folder / "unrelated.txt").write_text("must not be archived")
        archive = batch.archive()
        with zipfile.ZipFile(archive) as z:
            self.assertEqual(set(z.namelist()), {"photo_001.jpg", "photo_002.jpg", "manifest.json"})
            self.assertEqual(z.read("photo_001.jpg"), self.jpeg)
            manifest = json.loads(z.read("manifest.json"))
            self.assertEqual(len(manifest["photos"]), 2)
        self.assertTrue((batch.folder / "photo_001.jpg").exists())

    def test_invalid_image_does_not_consume_photo_number(self):
        batch = PhotoBatch(self.root)
        with self.assertRaises(OSError):
            batch.save(b"not a photo", "photo")
        self.assertEqual(batch.save(self.jpeg, "photo").name, "photo_001.jpg")

    def test_batches_use_separate_folders_and_existing_zip_is_not_overwritten(self):
        a = PhotoBatch(self.root)
        b = PhotoBatch(self.root)
        self.assertNotEqual(a.folder, b.folder)
        a.archive()
        with self.assertRaises(FileExistsError):
            a.archive()

    def test_capture_retry_then_ctrl_c_saves_zip_and_restores_robot(self):
        nao, link, trigger = Mock(), Mock(), Mock()
        trigger.requests.get.side_effect = [0, 0, KeyboardInterrupt]
        captures = []

        def capture(n, l, path):
            captures.append(path)
            if len(captures) == 1:
                raise RuntimeError("Transient camera failure")
            path.write_bytes(self.jpeg)
            return "photo"

        with patch("nao_proxy.connect_robot", return_value=object()), patch("nao_proxy.NaoProxy", return_value=nao), patch("robot_link.RobotLink", return_value=link), patch("photo_mode.HeadCaptureTrigger", return_value=trigger), patch("photo_mode.capture_robot", side_effect=capture), patch("photo_mode.time.sleep"), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_photo_mode("robot", self.root), 0)
        nao.subscribe.assert_called_once_with("FrontTactilTouched", trigger.touch)
        nao.restore_movement.assert_called_once()
        link.close.assert_called_once()
        archives = list(self.root.glob("*.zip"))
        self.assertEqual(len(archives), 1)
        with zipfile.ZipFile(archives[0]) as z:
            self.assertEqual(set(z.namelist()), {"manifest.json", "photo_001.jpg"})
        self.assertEqual(trigger.finish.call_count, 2)


if __name__ == "__main__":
    unittest.main()
