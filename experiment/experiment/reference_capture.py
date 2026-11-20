"""Head taps request captures; image capture and disk writes stay off the sensor callback."""
import json
from pathlib import Path
import queue
import threading
import time

import config
from build_workflow import ACTIVITIES, read_json


class HeadCaptureTrigger:
    def __init__(self, debounce_s=0.7):
        self.requests = queue.Queue(maxsize=1)
        self.lock = threading.Lock()
        self.down = False
        self.armed = False
        self.busy = False
        self.last = -1e9
        self.debounce_s = debounce_s

    def touch(self, value, now=None):
        now = time.monotonic() if now is None else now
        pressed = value is not None and float(value) > 0.5
        with self.lock:
            was_down = self.down
            self.down = pressed
            if pressed and not was_down:
                self.armed = not self.busy
            #Capture on release, after the hand has moved away from NAO's head.
            if not pressed and was_down and self.armed and not self.busy and now - self.last >= self.debounce_s:
                self.last = now
                self.busy = True
                self.requests.put_nowait(now)
            if not pressed:
                self.armed = False

    def finish(self):
        with self.lock:
            self.busy = False


def capture_robot(nao, link, path):
    errors = []
    methods = {"auto": ("photo", "video"), "photo": ("photo",), "video": ("video",)}[config.CAPTURE_METHOD]
    for method in methods:
        try:
            if method == "photo":
                remote = nao.capture_photo()
                link.get(remote, str(path))
                link.remove(remote)
            else:
                nao.capture_video_frame().save(path, "JPEG", quality=95)
            return method
        except Exception as e:
            errors.append(f"{method}: {e}")
    raise RuntimeError("Capture failed: " + "; ".join(errors))


def save_reference(root, activity, number, jpeg, capture_info, instruction=None, expected=None):
    """Never overwrite a reference. New steps remain drafts until manually reviewed."""
    if activity not in ACTIVITIES or number < 1:
        raise ValueError("Choose tutorial/build_1/build_2/build_3 and a positive step number")
    folder = Path(root) / activity
    spec_path = folder / "build.json"
    spec = read_json(spec_path)
    if spec.get("mode") == "controls":
        raise ValueError("The controls tutorial does not use reference photos; choose a build instead")
    if not isinstance(spec.get("steps"), list):
        raise ValueError("build.json must have a steps list")
    name = f"step_{number:02d}"
    step_dir = folder / name
    step_dir.mkdir(parents=True, exist_ok=True)
    photo = step_dir / "reference.jpg"
    #Validate before touching metadata or adding the step to the manifest.
    import io
    from PIL import Image
    with Image.open(io.BytesIO(jpeg)) as image:
        image.verify()
    step_path = step_dir / "step.json"
    step = read_json(step_path) if step_path.exists() else dict(instruction="", expected="")
    step.update(reference_photo="reference.jpg", ready=False)
    if instruction is not None:
        step["instruction"] = instruction
    if expected is not None:
        step["expected"] = expected
    with photo.open("xb") as f:
        f.write(jpeg)
    step_path.write_text(json.dumps(step, indent=2) + "\n", encoding="utf-8")
    (step_dir / "capture.json").write_text(json.dumps(capture_info, indent=2) + "\n", encoding="utf-8")
    if name not in spec["steps"]:
        spec["steps"].append(name)
        spec["steps"].sort(key=lambda s: int(s.removeprefix("step_")))
        spec_path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    return photo
