"""Standalone head-tap photo collection, with one ZIP for manual upload."""
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import queue
import time
import zipfile

import config
from reference_capture import HeadCaptureTrigger, capture_robot

PHOTO_DIR = Path(config.EXPERIMENT_DIR) / "photo_sessions"


class PhotoBatch:
    def __init__(self, output_root=PHOTO_DIR):
        root = Path(output_root).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.folder = root / datetime.now(timezone.utc).strftime("photos_%Y%m%d_%H%M%S_%f")
        self.folder.mkdir()
        self.records = []
        self.write_manifest()

    def write_manifest(self):
        (self.folder / "manifest.json").write_text(json.dumps({
            "purpose": "Unassigned robot photos for manual upload; not approved build references.",
            "camera_index": config.CAMERA_INDEX, "head_pitch": config.HEAD_PITCH,
            "head_yaw": config.HEAD_YAW, "posture": config.POSTURE,
            "photos": self.records}, indent=2) + "\n", encoding="utf-8")

    def save(self, jpeg, method):
        from PIL import Image
        with Image.open(io.BytesIO(jpeg)) as image:
            image.verify()
        name = f"photo_{len(self.records) + 1:03d}.jpg"
        path = self.folder / name
        with path.open("xb") as f:
            f.write(jpeg)
        self.records.append(dict(filename=name, capture_method=method,
                                 captured_at=datetime.now(timezone.utc).isoformat()))
        self.write_manifest()
        return path

    def archive(self):
        self.write_manifest()
        path = self.folder.with_suffix(".zip")
        with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(self.folder / "manifest.json", "manifest.json")
            for photo in self.records:
                archive.write(self.folder / photo["filename"], photo["filename"])
        return path


def run_photo_mode(robot_ip, output_root=PHOTO_DIR):
    #No OpenAI client, key loading, participant session or authored-build validation.
    from nao_proxy import connect_robot, NaoProxy
    from robot_link import RobotLink
    session = connect_robot(robot_ip)
    if session is None:
        return 1
    nao = NaoProxy(session)
    link = None
    batch = PhotoBatch(output_root)
    scratch = batch.folder / ".pending.jpg"
    trigger = HeadCaptureTrigger()
    try:
        link = RobotLink(robot_ip)
        nao.quiet_movement()
        nao.prepare_posture()
        nao.set_head_pose(wait=True)
        if not nao.subscribe("FrontTactilTouched", trigger.touch):
            raise RuntimeError("Could not subscribe to the front head sensor")
        print("PHOTO MODE — do not run a participant session or another camera tool at the same time.")
        print("Tap and release the FRONT HEAD sensor for each photo. Ctrl+C stops and makes an upload ZIP.")
        print("No API key, participant ID or build setup is needed. Bumpers and conversation are inactive.")
        print(f"Saving photos to: {batch.folder}")
        while True:
            try:
                trigger.requests.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                time.sleep(0.8)
                nao.set_head_pose(wait=True)
                method = capture_robot(nao, link, scratch)
                photo = batch.save(scratch.read_bytes(), method)
                print(f"Saved {photo.name} ({len(batch.records)} photos). Arrange the next state and tap again.")
            except Exception as e:
                print(f"Photo not saved: {e}. Fix the problem and tap again.")
            finally:
                scratch.unlink(missing_ok=True)
                trigger.finish()
    except KeyboardInterrupt:
        print("\nPhoto collection stopped.")
    except Exception as e:
        print(f"Photo mode stopped: {e}")
        return 1
    finally:
        scratch.unlink(missing_ok=True)
        try:
            nao.restore_movement()
        finally:
            try:
                if link:
                    link.close()
            finally:
                try:
                    archive = batch.archive()
                    print(f"Upload this ZIP ({len(batch.records)} photos): {archive}")
                    print(f"Original photos are also kept in: {batch.folder}")
                except Exception as e:
                    print(f"Could not make ZIP: {e}. Your saved photos remain in {batch.folder}")
    return 0
