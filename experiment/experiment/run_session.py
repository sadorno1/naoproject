#entry point for one experiment session.
#usage: python run_session.py --ip <robot_ip> --pid <participant_id> --condition {ai,human} [--force-new]
#       python run_session.py --dry-run --pid test01 --condition ai --image test_photos/correct/x.jpg [--no-tts]
#the condition is ONLY written to the log; nothing else in the session reads it
import argparse
import hashlib
import os
import re
import shutil
import sys
import threading
import time

import config
from session_log import SessionLog, StageTimer, ParticipantFolderExists
from inputs import InputManager, CHECKING, ENDED


def load_fixed_lines(path=config.FIXED_LINES_PATH):
    import json
    with open(path, "r", encoding="utf-8") as f:
        lines = json.load(f)
    if (not lines.get("greeting") or not lines.get("goodbye") or not lines.get("early_goodbye")
            or len(lines.get("look", [])) != 3):
        raise ValueError("fixed_lines.json needs greeting, goodbye, early_goodbye and exactly 3 look lines")
    return lines


#files that must be edited before a real session; returns a list of problems
def placeholder_problems():
    problems = []
    for path in (config.FIXED_LINES_PATH, config.TARGET_DESCRIPTION_PATH, config.TARGET_STRUCTURE_PATH):
        with open(path, "r", encoding="utf-8") as f:
            if config.PLACEHOLDER_MARKER in f.read():
                problems.append(f"{os.path.relpath(path, config.EXPERIMENT_DIR)} still contains "
                                f"'{config.PLACEHOLDER_MARKER}' placeholders")
    return problems


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def config_snapshot():
    return {k: getattr(config, k) for k in dir(config) if k.isupper() and not k.endswith("_PATH")
            and not k.endswith("_DIR")}


class Session:
    def __init__(self, args):
        import vision
        from dialogue import DialogueModel, build_system_prompt
        from nao_proxy import NaoProxy, connect_robot
        from robot_link import RobotLink, LocalLink
        from speech import TTS, SpeechPipeline
        from transcribe import Transcriber

        self.args = args
        self.vision = vision
        self.dry_run = args.dry_run
        self.fixed = load_fixed_lines()
        self.workflow = None
        if not args.legacy_build:
            from build_workflow import BuildWorkflow, workflow_system_prompt
            self.workflow = BuildWorkflow(root=args.builds_dir, only=args.activity)
            system_prompt = workflow_system_prompt()
            self.prompt_sha = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()
        else:
            self.schema = vision.load_schema()
            self.target = vision.load_target(schema=self.schema)
            self.reference_jpeg = (vision.preprocess_image(config.REFERENCE_PHOTO_PATH)
                                   if config.REFERENCE_PHOTO_PATH else None)
            system_prompt, self.prompt_sha = build_system_prompt()

        from dotenv import load_dotenv
        from openai import OpenAI
        load_dotenv(config.DOTENV_PATH)
        self.client = OpenAI()

        self.log = SessionLog(config.DATA_DIR, args.pid, force_new=args.force_new)
        print(f"Logging to {self.log.path}")

        session = None if self.dry_run else connect_robot(args.ip)
        if not self.dry_run and session is None:
            self.log.event("session_abort", reason="robot_not_connected")
            self.log.close()
            raise SystemExit("Could not connect to the robot. Use --dry-run to test without it.")
        self.nao = NaoProxy(session)
        self.link = LocalLink() if self.dry_run else RobotLink(args.ip)

        self.log.event(
            "session_start",
            participant_id=args.pid,
            condition=args.condition,
            dry_run=self.dry_run,
            robot_ip=None if self.dry_run else args.ip,
            naoqi_version=self.nao.naoqi_version(),
            system_prompt_sha256=self.prompt_sha,
            target_structure_sha256=None if self.workflow else sha256_file(config.TARGET_STRUCTURE_PATH),
            target_description_sha256=None if self.workflow else sha256_file(config.TARGET_DESCRIPTION_PATH),
            fixed_lines_sha256=sha256_file(config.FIXED_LINES_PATH),
            reference_photo=None if self.workflow else config.REFERENCE_PHOTO_PATH,
            config=config_snapshot(),
            workflow_steps=self.workflow.steps if self.workflow else None,
        )

        self.dialogue = DialogueModel(self.client, system_prompt)
        self.transcriber = Transcriber(self.client)
        self.speech = SpeechPipeline(self.nao, self.link, TTS(self.client), dry_run=self.dry_run,
                                     synthesize=not args.no_tts)
        self.inputs = InputManager(self.log)
        self.inputs.on_barge_in = self._barge_in

        self.identity_patterns = [re.compile(p, re.I) for p in config.IDENTITY_QUESTION_PATTERNS]
        self.turn = 0
        self.checks = 0
        self.current_utterance = None
        self.task_start = None
        self.session_start = time.perf_counter()
        self.ended = False
        self.talk_press_t = None

    # ------------------------------------------------------------ setup / teardown
    def setup(self):
        self.nao.quiet_movement()
        self.nao.prepare_posture()
        self.nao.set_volume()
        self.nao.set_head_pose()
        self.nao.set_eyes(config.EYES_IDLE_RGB)
        print("Preparing cached audio for fixed lines...")
        self.speech.prepare_fixed([self.fixed["greeting"], *self.fixed["look"], self.fixed["goodbye"],
                                   self.fixed["early_goodbye"]])
        if not self.dry_run:
            subscribed = self.inputs.attach(self.nao)
            self.log.event("sensors_subscribed", keys=subscribed)
            if config.TALK_SENSOR_KEY not in subscribed:
                raise SystemExit(f"Could not subscribe to {config.TALK_SENSOR_KEY}; run tools/sensor_probe.py")
        self._start_keyboard_thread()

    def _start_keyboard_thread(self):
        if self.dry_run:
            target = self._dry_run_reader
            print("\nDry run. Type what the participant says and press Enter.\n"
                  "  /check [image_path]  simulate a bumper press\n"
                  "  /end                 experimenter ends the session\n")
        else:
            target = self._experimenter_key_reader
            print(f"\nPress '{config.EXPERIMENTER_END_KEY}' to end the session (logged as experimenter).\n")
        threading.Thread(target=target, daemon=True).start()

    def _experimenter_key_reader(self):
        try:
            import msvcrt
            while not self.ended:
                if msvcrt.kbhit() and msvcrt.getwch().lower() == config.EXPERIMENTER_END_KEY:
                    self.inputs.request_end("experimenter")
                    return
                time.sleep(0.05)
        except ImportError:
            #not on Windows: fall back to a line-based read
            while not self.ended:
                if sys.stdin.readline().strip().lower() == config.EXPERIMENTER_END_KEY:
                    self.inputs.request_end("experimenter")
                    return

    def _dry_run_reader(self):
        while not self.ended:
            try:
                line = input().strip()
            except EOFError:
                self.inputs.request_end("experimenter")
                return
            t = time.perf_counter()
            if line == "/end":
                self.inputs.request_end("experimenter", t)
                return
            if line.startswith("/check"):
                path = line[len("/check"):].strip()
                if path:
                    self.args.image = path
                self.inputs.on_check("DryRunCheck", 1.0, t)
                self.inputs.on_check("DryRunCheck", 0.0, time.perf_counter())
            elif line:
                self.inputs.on_typed(line, t)

    def _barge_in(self):
        if self.current_utterance is not None:
            self.current_utterance.cancel()
            self.log.event("barge_in")

    # ------------------------------------------------------------ main loop
    def run(self):
        import queue
        self.setup()
        self._say_fixed("greeting", self.fixed["greeting"], config.GREETING_GESTURE)
        self.task_start = time.perf_counter()
        self.log.event("task_start", t_perf=self.task_start)

        if self.workflow:
            self.inputs.set_state("processing")
            self._announce_step()
            self.inputs.finish_busy()
        elif config.FIRST_STEP_AFTER_GREETING:
            self.inputs.set_state("processing")
            self.turn += 1
            timer = StageTimer(self.log, "turn", self.turn)
            self._respond("[SESSION START] The greeting has already been said. Give the first build step.",
                          timer, source="session_start")
            self.inputs.finish_busy()

        while not self.ended:
            if config.HARD_CAP_MINUTES and time.perf_counter() - self.task_start > config.HARD_CAP_MINUTES * 60:
                self.end("hard_cap", say_goodbye=config.SAY_GOODBYE_ON_HARD_CAP)
                break
            try:
                kind, t, payload = self.inputs.events.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                if kind == "talk_press":
                    self._talk_press(t)
                elif kind == "talk_release":
                    self._talk_release(t)
                elif kind == "typed":
                    self._typed(t, payload)
                elif kind == "check":
                    self._check(t, payload)
                elif kind == "end":
                    self.end(payload, say_goodbye=config.SAY_GOODBYE_ON_EXPERIMENTER_END)
            except Exception as e:
                #never crash mid-session: log, reset to idle, keep listening
                print(f"ERROR handling {kind}: {e}")
                self.log.event("error", during=kind, error=repr(e))
                self.nao.set_eyes(config.EYES_IDLE_RGB)
                self.inputs.finish_busy()
                if self.inputs.state == "recording":
                    self.inputs.set_state("idle")

    def end(self, reason, say_goodbye=True):
        if self.ended:
            return
        self.ended = True
        self.inputs.set_state(ENDED)
        if say_goodbye:
            workflow = getattr(self, "workflow", None)
            early = reason == "experimenter" and (workflow is None or not workflow.complete)
            kind = "early_goodbye" if early else "goodbye"
            try:
                self._say_fixed(kind, self.fixed[kind], config.GOODBYE_GESTURE)
            except Exception as e:
                #A playback failure must not prevent session logging or robot cleanup.
                self.log.event("goodbye_error", kind=kind, error=repr(e))
        t_end = time.perf_counter()
        self.log.event(
            "session_end",
            t_perf=t_end,
            end_reason=reason,
            session_duration_s=round(t_end - self.session_start, 3),
            task_completion_time_s=round(t_end - self.task_start, 3) if self.task_start else None,
            turns=self.turn,
            checks=self.checks,
        )
        self.nao.set_eyes(config.EYES_IDLE_RGB)
        self.nao.stop_gestures()
        self.nao.wait_for_gestures()
        self.nao.restore_movement()
        self.link.cleanup()
        self.link.close()
        self.log.close()
        print(f"Session ended ({reason}). Log: {self.log.path}")

    # ------------------------------------------------------------ talking
    def _talk_press(self, t):
        self.talk_press_t = t
        self.nao.set_eyes(config.EYES_RECORDING_RGB)
        self.nao.start_recording(config.ROBOT_RECORDING_PATH)
        self.log.event("recording_start", t_perf=t)

    def _talk_release(self, t_release):
        self.nao.stop_recording()
        self.nao.set_eyes(config.EYES_IDLE_RGB)
        held = t_release - self.talk_press_t if self.talk_press_t else None
        self.log.event("recording_stop", t_perf=t_release, held_s=round(held, 3) if held else None)
        if held is not None and held < config.MIN_HOLD_S:
            self.link.remove(config.ROBOT_RECORDING_PATH)
            self.log.event("recording_discarded", reason="hold_too_short", held_s=round(held, 3))
            self.inputs.finish_busy()
            return

        self.turn += 1
        timer = StageTimer(self.log, "turn", self.turn, t_start=t_release)
        timer.mark("touch_release", t_release)
        local_wav = os.path.join(config.TMP_DIR, "recording.wav")
        os.makedirs(config.TMP_DIR, exist_ok=True)
        try:
            self.link.get(config.ROBOT_RECORDING_PATH, local_wav)
            timer.mark("wav_transfer")
            text = self.transcriber.transcribe(local_wav)
            timer.mark("transcription")
        finally:
            #raw audio is never kept: delete it on both sides right after transcription
            for remove in (lambda: os.remove(local_wav), lambda: self.link.remove(config.ROBOT_RECORDING_PATH)):
                try:
                    remove()
                except Exception:
                    pass
            self.log.event("audio_deleted", turn=self.turn)

        self._handle_participant_text(text, timer, source="speech", held_s=held)
        self.inputs.finish_busy()

    def _typed(self, t, text):
        self.turn += 1
        timer = StageTimer(self.log, "turn", self.turn, t_start=t)
        timer.mark("touch_release", t)
        self._handle_participant_text(text, timer, source="typed")
        self.inputs.finish_busy()

    def _handle_participant_text(self, text, timer, source, held_s=None):
        self.log.event("participant_utterance", turn=self.turn, text=text, source=source,
                       transcribe_backend=None if source == "typed" else config.TRANSCRIBE_BACKEND,
                       held_s=round(held_s, 3) if held_s else None)
        print(f"\nParticipant: {text!r}")
        matched = [p.pattern for p in self.identity_patterns if text and p.search(text)]
        if matched:
            self.log.event("identity_question", turn=self.turn, text=text, patterns=matched)
        if (text and getattr(self, "workflow", None)
                and self.workflow.current.get("completion") == "talk"):
            step = self.workflow.current
            self.log.event("tutorial_control_passed", step_id=step["step_id"], control="talk", source=source)
            self._complete_current_step(step, timer)
            return
        if not text:
            if config.EMPTY_TRANSCRIPT_MESSAGE is None:
                self.log.event("empty_transcript_ignored", turn=self.turn)
                timer.write(skipped="empty_transcript")
                return
            text = config.EMPTY_TRANSCRIPT_MESSAGE
        self._respond(text, timer, source=source)

    #streams the model reply: gesture on line 1, then speech sentence by sentence
    def _respond(self, content, timer, source):
        if getattr(self, "workflow", None):
            content = self.workflow.dialogue_context() + "\n\n" + content
        utterance = self.speech.start_utterance(f"turn{self.turn:03d}", timer,
                                                on_playback_start=self.inputs.mark_speaking)
        self.current_utterance = utterance

        def on_expression(name):
            path, status = self.nao.change_expression(name)
            self.log.event("gesture", turn=self.turn, expression=name, behavior=path, status=status)

        try:
            result = self.dialogue.stream_reply(content, on_expression, utterance.add, timer=timer,
                                                should_stop=utterance.cancelled.is_set)
        except Exception as e:
            utterance.close()
            utterance.wait()
            self.current_utterance = None
            self.log.event("llm_error", turn=self.turn, error=repr(e))
            print(f"LLM ERROR: {e}")
            timer.write(error="llm")
            return
        utterance.close()
        played = utterance.wait()
        self.current_utterance = None
        print(f"Robot [{result['expression']}]: {result['speech']}")
        self.log.event("robot_utterance", turn=self.turn, kind="llm", in_reply_to=source,
                       text=result["speech"], expression=result["expression"], sentences=result["sentences"],
                       sentences_played=played["played"], cancelled=played["cancelled"], errors=played["errors"],
                       format_violations=result["format_violations"], raw=result["raw"], model=config.LLM_MODEL)
        timer.write(llm_total_s=result["llm_total_s"])

    def _say_fixed(self, kind, text, gesture=None):
        if gesture:
            path, status = self.nao.change_expression(gesture)
            self.log.event("gesture", turn=self.turn, expression=gesture, behavior=path, status=status)
        t = self.speech.play_fixed(text)
        self.log.event("robot_utterance", t_perf=t, turn=self.turn, kind=f"fixed_{kind}", text=text,
                       expression=gesture)

    # ------------------------------------------------------------ build check
    def _check(self, t_press, key):
        if getattr(self, "workflow", None):
            return self._check_step(t_press, key)
        self.checks += 1
        n = self.checks
        timer = StageTimer(self.log, "check", n, t_start=t_press)
        timer.mark("bumper_press", t_press)
        self.log.event("check_start", t_perf=t_press, check=n, key=key)

        look = self.fixed["look"][(n - 1) % len(self.fixed["look"])]
        self.inputs.mark_speaking()
        self._say_fixed("look", look, config.LOOK_GESTURE)
        timer.mark("look_line_done")
        self.inputs.set_state(CHECKING)
        raw_path = self.log.image_path(n)
        try:
            gestures_done = self.nao.wait_for_gestures()
            if not gestures_done:
                self.nao.stop_gestures()
                gestures_done = self.nao.wait_for_gestures()
            if not gestures_done:
                raise RuntimeError("Robot is still moving; camera check deferred")
            if config.REASSERT_HEAD_POSE_BEFORE_PHOTO and not self.dry_run:
                self.nao.set_head_pose(wait=True)
            method = self._capture(raw_path)
            timer.mark("capture_done")
            jpeg = self.vision.preprocess_image(raw_path)
            with open(self.log.image_path(n, "_sent"), "wb") as f:
                f.write(jpeg)
            observation, info = self.vision.extract_build(self.client, jpeg, reference_jpeg=self.reference_jpeg,
                                                          schema=self.schema)
            timer.mark("vision_done")
            diff = self.vision.compare_build(observation, self.target)
        except Exception as e:
            self.log.event("check_error", check=n, error=repr(e))
            print(f"CHECK ERROR: {e}")
            timer.write(error="check")
            self.turn += 1
            self._respond("[BUILD CHECK RESULT]\nThe camera check failed this time, so nothing about the build "
                          "is known. The participant can ask for another check.", timer, source="check_error")
            self.inputs.finish_busy()
            return

        self.log.event("check_result", check=n, match=diff["match"], counts=diff["counts"],
                       diff=self.vision.diff_for_log(diff), observation=observation, image=raw_path,
                       capture_method=method, gestures_finished_before_photo=gestures_done,
                       vision={k: v for k, v in info.items() if k != "raw"})
        print(f"Check {n}: match={diff['match']} counts={diff['counts']}")
        if diff["match"]:
            timer.write()
            self.end("build_complete", say_goodbye=True)
            return
        self.turn += 1
        self._respond(self.vision.describe_diff(diff), timer, source="check")
        self.inputs.finish_busy()

    def _announce_step(self):
        step = self.workflow.current
        self.log.event("step_start", activity=step["activity"], step_id=step["step_id"],
                       reference_sha256=step["reference_sha256"])
        #Discard dialogue history from the previous step/activity.
        from dialogue import DialogueModel
        from build_workflow import workflow_system_prompt
        self.dialogue = DialogueModel(self.client, workflow_system_prompt())
        self._say_fixed("step_instruction", self.workflow.announcement())

    def _say_workflow_feedback(self, step, kind, reason="", next_title=None):
        from workflow_feedback import generate_feedback
        fallbacks = {
            "step_correct": "That's correct, nice work! Let's move on to the next step.",
            "activity_complete": f"You finished {step['title']}, great work! Let's start {next_title}.",
            "session_complete": "Wonderful work, you've finished all the activities in this session! Thank you for building with me.",
            "retry": "Not quite yet. " + (step.get("hint") or "Let's check the placement against the instruction and try again."),
        }
        try:
            text = generate_feedback(self.client, step, kind, reason, next_title)
            fallback = False
        except Exception as e:
            self.log.event("feedback_error", kind=kind, error=repr(e))
            text, fallback = fallbacks[kind], True
        self.log.event("workflow_feedback", activity=step["activity"], step_id=step["step_id"],
                       kind=kind, text=text, fallback=fallback, model=config.LLM_MODEL)
        self._say_fixed("workflow_" + kind, text)

    def _check_step(self, t_press, key):
        from step_vision import compare_step
        self.checks += 1
        n = self.checks
        step = self.workflow.current
        timer = StageTimer(self.log, "check", n, t_start=t_press)
        timer.mark("bumper_press", t_press)
        self.log.event("check_start", check=n, key=key, activity=step["activity"], step_id=step["step_id"])
        if step.get("completion") == "talk":
            self._say_fixed("tutorial_reminder", "We'll practice checking next. First, hold my right foot bumper while you speak, then let go.")
            timer.write(skipped="tutorial_talk_first")
            self.inputs.finish_busy()
            return
        try:
            self._say_fixed("look", self.fixed["look"][(n - 1) % len(self.fixed["look"])])
            self.inputs.set_state(CHECKING)
            if not self.nao.wait_for_gestures():
                self.nao.stop_gestures()
                if not self.nao.wait_for_gestures():
                    raise RuntimeError("Robot is still moving")
            if not self.dry_run:
                self.nao.set_head_pose(wait=True)
            path = self.log.image_path(n)
            method = self._capture(path)
            current = self.vision.preprocess_image(path)
            with open(self.log.image_path(n, "_sent"), "wb") as f:
                f.write(current)
            if step.get("completion") == "check":
                result = {"verdict": "yes", "reason": "Check control practiced and photo captured; no build correctness evaluated."}
                info = {"mode": "controls_tutorial"}
            else:
                reference = self.vision.preprocess_image(step["reference_photo"])
                #Fail closed if a reference is edited during the session.
                if sha256_file(step["reference_photo"]) != step["reference_sha256"]:
                    raise RuntimeError("Reference changed; restart the session to load the updated workflow")
                result, info = compare_step(self.client, current, reference, step["expected"])
            self.log.event("step_check_result", check=n, activity=step["activity"], step_id=step["step_id"],
                           result=result, vision=info, image=path, capture_method=method,
                           reference_sha256=step["reference_sha256"])
        except Exception as e:
            self.log.event("check_error", check=n, activity=step["activity"], step_id=step["step_id"], error=repr(e))
            timer.write(error="step_check")
            self._say_fixed("check_failed", "I couldn't check that photo. Please clear the view and press my left foot bumper to try again.")
            self.inputs.finish_busy()
            return
        timer.mark("vision_done")
        verdict = result["verdict"]
        if verdict == "yes":
            self._complete_current_step(step, timer)
            return
        elif verdict == "no":
            self._say_workflow_feedback(step, "retry", reason=result["reason"])
            self._say_fixed("step_instruction", self.workflow.announcement(include_start=False))
        else:
            self._say_fixed("step_uncertain", "I can't see clearly enough to check. Move your hands away and press my left foot bumper to try again.")
        timer.write()
        self.inputs.finish_busy()

    def _complete_current_step(self, step, timer):
        last_in_activity = step["number"] == step["count"]
        finished = self.workflow.advance("yes")
        if finished:
            self._say_workflow_feedback(step, "session_complete")
            timer.write()
            self.end("workflow_complete", say_goodbye=False)
            return
        if last_in_activity:
            self._say_workflow_feedback(step, "activity_complete", next_title=self.workflow.current["title"])
        else:
            self._say_workflow_feedback(step, "step_correct")
        self._announce_step()
        timer.write()
        self.inputs.finish_busy()

    #saves the camera image to local_path; returns the method used
    def _capture(self, local_path):
        if self.dry_run:
            if not self.args.image:
                raise RuntimeError("dry run needs --image or /check <path>")
            shutil.copyfile(self.args.image, local_path)
            return "dry_run_file"
        methods = {"auto": ("photo", "video"), "photo": ("photo",), "video": ("video",)}[config.CAPTURE_METHOD]
        errors = []
        for method in methods:
            try:
                if method == "photo":
                    robot_path = self.nao.capture_photo()
                    self.link.get(robot_path, local_path)
                    self.link.remove(robot_path)
                else:
                    self.nao.capture_video_frame().save(local_path, "JPEG", quality=95)
                return method
            except Exception as e:
                errors.append(f"{method}: {e}")
                self.log.event("capture_fallback", method=method, error=repr(e))
        raise RuntimeError("capture failed: " + " | ".join(errors))


def parse_args(argv=None):
    from build_workflow import BUILDS_DIR, ACTIVITIES
    parser = argparse.ArgumentParser(description="Run one Mega Bloks build session with the NAO.")
    parser.add_argument("--ip", help="robot IP (not needed with --dry-run)")
    parser.add_argument("--pid", required=True, help="participant ID (also the data folder name)")
    parser.add_argument("--condition", required=True, choices=["ai", "human"],
                        help="study condition; only written to the log")
    parser.add_argument("--force-new", action="store_true",
                        help="if the participant folder exists, create a timestamped subfolder instead of refusing")
    parser.add_argument("--dry-run", action="store_true", help="typed input and a local image, no robot")
    parser.add_argument("--image", help="dry run: image file used for build checks")
    parser.add_argument("--no-tts", action="store_true", help="dry run: print robot speech instead of synthesizing it")
    parser.add_argument("--builds-dir", default=str(BUILDS_DIR), help="folder containing tutorial and three builds")
    parser.add_argument("--activity", choices=ACTIVITIES, help="optional single activity for rehearsal; default runs all four")
    parser.add_argument("--legacy-build", action="store_true", help="run the old single four-block demo")
    args = parser.parse_args(argv)
    if not args.dry_run and not args.ip:
        parser.error("--ip is required unless --dry-run is set")
    if args.no_tts and not args.dry_run:
        parser.error("--no-tts is only allowed with --dry-run")
    if args.legacy_build and args.activity:
        parser.error("--activity cannot be used with --legacy-build")
    return args


def main(argv=None):
    args = parse_args(argv)
    if not args.dry_run and args.legacy_build:
        problems = placeholder_problems()
        if problems:
            print("Not ready for a real session:")
            for p in problems:
                print(f"  - {p}")
            return 1
    try:
        session = Session(args)
    except ParticipantFolderExists as e:
        print(e)
        return 1
    except (ValueError, OSError) as e:
        print(f"Not ready: {e}")
        return 1
    try:
        session.run()
    except KeyboardInterrupt:
        session.end("keyboard_interrupt", say_goodbye=False)
    except Exception as e:
        session.log.event("fatal_error", error=repr(e))
        session.end("fatal_error", say_goodbye=False)
        raise
    finally:
        #Also restore settings if setup exits early (for example, a missing sensor).
        session.nao.restore_movement()
    return 0


if __name__ == "__main__":
    sys.exit(main())
