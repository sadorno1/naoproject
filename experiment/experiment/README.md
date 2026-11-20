# NAO experiment code

The current participant flow is:

**Talk practice → check practice → tutorial mini build → build 1 → build 2 → build 3.**

The tutorial is finished only after its mini build passes. Each construction step needs your instruction, expected-state description and approved robot reference photo. The mini-build and main-build placements are drafts until you author them.

See the [main README](../../README.md) for installation, API key setup, current controls, camera setup and run commands. See [BUILD_WORKFLOW.md](../../BUILD_WORKFLOW.md) for the detailed step structure, author-only capture workflow and JSON examples.

## Controls in the participant session

- Hold NAO's **right foot bumper** to talk; release to send. Eyes are green while recording.
- Press NAO's **left foot bumper** to request a check.
- NAO's head sensor is inactive. Head tapping is only used in the separate authoring tool.
- Foot sides mean NAO's own sides, mirrored when facing it.
- Press `q` in the terminal to end early.

## Commands from this folder

Configure the API key:

```bash
python ../../setup_keys.py
```

It saves the key in `../.env` (the repository's `experiment/.env`), which Git ignores. Restart running sessions after replacing it.

Check sensors and camera:

```bash
python tools/sensor_probe.py ROBOT_IP
```

Stop the sensor probe with Ctrl+C before continuing:

```bash
python tools/camera_probe.py ROBOT_IP --set-head --camera 0 --out tmp/camera_top
python tools/camera_probe.py ROBOT_IP --set-head --camera 1 --out tmp/camera_bottom
```

Review the saved images and save the successful camera/head settings in `config.py`. Use those same settings when capturing references.

Capture reference photos, one activity at a time, with no participant session running:

```bash
python tools/capture_build_steps.py ROBOT_IP --build tutorial
python tools/capture_build_steps.py ROBOT_IP --build build_1
python tools/capture_build_steps.py ROBOT_IP --build build_2
python tools/capture_build_steps.py ROBOT_IP --build build_3
```

In this authoring tool only, tap and release the front head sensor after arranging each cumulative placement. The tutorial starts at `step_03`; the first two steps are control exercises. Ctrl+C stops. Existing photos are not overwritten. Review each photo, fill its neighboring `step.json`, and set `ready` to true.

After authoring the steps:

```bash
python tools/pregenerate_audio.py
python run_session.py --ip ROBOT_IP --pid P01 --condition ai
```

For one activity:

```bash
python run_session.py --ip ROBOT_IP --pid tutorial01 --condition ai --activity tutorial
```

The tutorial mini build must be ready even when running the tutorial alone. The three main builds may still be drafts in this rehearsal mode. The condition label (`ai` / `human`) is logged only and does not change the robot's implementation.

## Check results

Correct steps receive generated encouragement, then the next authored instruction. Completing an activity gets a celebration and introduction to the next one. Incorrect steps receive a brief hint followed by the same instruction. Uncertain or failed checks stay on the current step and request another try. The final activity ends with a celebration.

Saying “done” does not pass a construction step. During the tutorial's first exercise, understandable speech completes talking practice; during its second exercise, a successful capture completes check practice. Neither exercise judges a build. All later tutorial and main-build placements use photo comparisons.

## Logs and testing

`data/<pid>/events_<timestamp>.jsonl` records sensor events, transcripts, spoken responses, loaded steps, reference hashes, check results and feedback. Current-build photos are stored in the participant folder; raw microphone recordings are deleted after transcription. Inspect `step_check_result`, `workflow_feedback` and `tutorial_control_passed` for the new workflow. Reusing a participant ID requires `--force-new`.

From the repository root:

```bash
python -m unittest discover -s experiment/experiment/tests -v
```

Offline tests do not establish live recognition accuracy, hint quality or audio loudness. Rehearse every authored step with actual NAO photos before the participant session. The legacy evaluator `tools/eval_vision.py` does not evaluate the new step-photo workflow.

## Legacy mode

The old four-block checker is preserved explicitly:

```bash
python run_session.py --ip ROBOT_IP --pid old01 --condition ai --legacy-build
```

Its setup is in [MEGA_BLOKS_SETUP.md](../../MEGA_BLOKS_SETUP.md). Editing the old target JSON or using its generated illustration does not configure the current tutorial-and-three-build workflow.

## Demo video

[Earlier demo video](https://drive.google.com/file/d/1tWsVY2K5dTFUNsXjIQ5FXgopgV_XcIl8/view?usp=sharing)
