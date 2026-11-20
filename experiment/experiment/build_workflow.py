"""Author-supplied steps and deterministic tutorial -> three builds progression."""
import hashlib
import json
from pathlib import Path

import config

BUILDS_DIR = Path(config.EXPERIMENT_DIR) / "builds"
ACTIVITIES = ("tutorial", "build_1", "build_2", "build_3")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def inside(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Path escapes build folder: {relative}")
    return path


def required_text(value, field):
    if not isinstance(value, str) or not value.strip() or "TODO" in value:
        raise ValueError(f"Fill in {field} before running this build")
    return value.strip()


class BuildWorkflow:
    def __init__(self, root=BUILDS_DIR, only=None):
        from PIL import Image
        self.steps = []
        for activity in ([only] if only else ACTIVITIES):
            if activity not in ACTIVITIES:
                raise ValueError(f"Unknown activity: {activity}")
            folder = Path(root) / activity
            spec = read_json(folder / "build.json")
            title = required_text(spec.get("title"), f"{activity} title")
            start = required_text(spec.get("start_instruction"), f"{activity} start_instruction")
            names = spec.get("steps")
            if (not isinstance(names, list) or not names or not all(isinstance(n, str) and n for n in names)
                    or len(set(names)) != len(names)):
                raise ValueError(f"{activity}: supply a nonempty ordered list of unique steps")
            mode = spec.get("mode", "photos")
            controls = mode in ("controls", "controls_and_build")
            if mode not in ("photos", "controls", "controls_and_build"):
                raise ValueError(f"Unknown activity mode: {mode}")
            if controls and activity != "tutorial":
                raise ValueError("Control practice is only supported in the tutorial")
            if mode == "controls" and len(names) != 2:
                raise ValueError("The controls tutorial must have two steps: talk practice then check practice")
            if mode == "controls_and_build" and len(names) < 3:
                raise ValueError("The tutorial needs talk practice, check practice and at least one mini-build step")
            for index, name in enumerate(names):
                step_dir = inside(folder, name)
                data = read_json(step_dir / "step.json")
                instruction = required_text(data.get("instruction"), f"{activity}/{name} instruction")
                expected = required_text(data.get("expected"), f"{activity}/{name} expected")
                hint = data.get("hint", "")
                if not isinstance(hint, str):
                    raise ValueError(f"{activity}/{name}: hint must be text")
                if controls and index < 2:
                    completion = data.get("completion")
                    if completion != ("talk" if index == 0 else "check"):
                        raise ValueError("Controls tutorial steps must complete on talk then check")
                    self.steps.append(dict(activity=activity, title=title, step_id=name,
                                           number=index + 1, count=len(names), instruction=instruction,
                                           expected=expected, hint=hint.strip(), completion=completion,
                                           reference_photo=None, capture=None, reference_sha256=None,
                                           start_instruction=start if index == 0 else None))
                    continue
                if data.get("completion"):
                    raise ValueError(f"{activity}/{name}: mini-build and main build steps must be photo checked")
                if data.get("ready") is not True:
                    raise ValueError(f"Review the photo and set ready=true in {activity}/{name}/step.json")
                photo = inside(step_dir, data.get("reference_photo", "reference.jpg"))
                with Image.open(photo) as image:
                    image.verify()
                metadata = step_dir / "capture.json"
                capture = read_json(metadata) if metadata.exists() else None
                if capture:
                    for field, actual in (("camera_index", config.CAMERA_INDEX), ("head_pitch", config.HEAD_PITCH),
                                          ("head_yaw", config.HEAD_YAW), ("posture", config.POSTURE)):
                        if capture.get(field) != actual:
                            raise ValueError(f"{activity}/{name}: {field} differs from reference capture; "
                                             "restore capture settings or retake the reference")
                self.steps.append(dict(activity=activity, title=title, step_id=name,
                                       number=index + 1, count=len(names), instruction=instruction,
                                       expected=expected, reference_photo=str(photo), capture=capture,
                                       hint=hint.strip(),
                                       start_instruction=(start if index == 0 else
                                           required_text(spec.get("mini_build_intro"), "tutorial mini_build_intro")
                                           if mode == "controls_and_build" and index == 2 else None),
                                       reference_sha256=hashlib.sha256(photo.read_bytes()).hexdigest()))
        self.index = 0

    @property
    def complete(self):
        return self.index == len(self.steps)

    @property
    def current(self):
        if self.complete:
            raise RuntimeError("All activities are complete")
        return self.steps[self.index]

    def advance(self, verdict):
        if verdict not in ("yes", "no", "uncertain"):
            raise ValueError("Invalid photo verdict")
        if verdict == "yes" and not self.complete:
            self.index += 1
        return self.complete

    def announcement(self, include_start=True):
        step = self.current
        prefix = f"{step['title']}. {step['start_instruction']} " if include_start and step["start_instruction"] else ""
        if step.get("completion"):
            return prefix + f"Step {step['number']}. {step['instruction']}"
        return (prefix + f"Step {step['number']}. {step['instruction']} "
                "When you are ready, move your hands away and press my left foot bumper to check.")

    def dialogue_context(self):
        step = self.current
        if step.get("completion"):
            return (f"[CURRENT STEP — controls tutorial]\nInstruction: {step['instruction']}\n"
                    "This is a walkthrough of robot controls, not a construction task. "
                    "Explain only the current control if asked. Do not ask them to place blocks or use "
                    "a head sensor. The session verifies the practiced interaction and advances automatically.")
        return (f"[CURRENT STEP — controlled by the session]\nActivity: {step['title']}. "
                f"Step {step['number']} of {step['count']}.\n"
                f"Instruction: {step['instruction']}\nExpected state: {step['expected']}\n"
                "Answer only questions about this step. Do not advance, invent another placement, "
                "or say the build is correct from the participant's words. Ask for a left-foot camera "
                "check when they are ready. The reference describes the expected state, not what is visible now.")


def workflow_system_prompt():
    return ("You are NAO helping a participant build Mega Bloks from author-supplied steps. "
            "The session controls step progression and speaks the instructions and photo verdicts. "
            "You answer participant questions about the CURRENT STEP only, in one or two short sentences. "
            "Do not invent inventory, positions, steps, or visual observations. Do not declare yes/no or "
            "advance from a participant saying done. When unsure, repeat the supplied instruction or ask "
            "for a left-foot camera check. Directions are the participant's view; do not reinterpret "
            "directions supplied by the author. Right foot bumper is hold-to-talk, release-to-send. "
            "Left foot bumper requests a check. Left/right foot names are NAO's own sides. "
            "Line 1 must be one expression from: " + ", ".join(config.EXPRESSIONS) +
            ". Remaining lines are only spoken words, without markdown.")
