# Tutorial and three builds

The default session runs **tutorial → build 1 → build 2 → build 3**, in that order. Each activity can have as many steps as you need. The old four-block demo remains available with `--legacy-build`.

## Where your material goes

```text
experiment/experiment/builds/
  tutorial/
    build.json
    step_01/
      step.json
      reference.jpg       # captured on your NAO; not supplied yet
      capture.json        # camera settings and capture timestamp
    step_02/              # created by the capture tool as you go
      ...
  build_1/
    build.json
    step_01/step.json
  build_2/
    build.json
    step_01/step.json
  build_3/
    build.json
    step_01/step.json
```

All four activities start with a blank, unapproved first step. No build designs or expected photos have been invented. You supply the photos and expected states. A new session refuses to start until all selected activities have reviewed steps, nonempty instructions, expected descriptions, and readable reference photos.

`build.json` contains a title, a spoken `start_instruction` (such as clearing the build area), and the ordered `steps` list. Every listed step is required. The tool appends newly captured steps to this list in numeric order. Edit the list if you want a different order or remove an unused step. Do not remove a step whose placement is required by a later reference unless you also update the instructions.

## Capture reference photos by tapping the head

Stop any running participant session first. Use the same robot posture, build spot, camera and head pose you plan to use during the session; set these in `config.py`. This tool uses those settings and restores background movement on exit. Camera/head/posture metadata is checked at session startup when available. Physical build placement and lighting still need a visual check.

On Linux, from the repository root:

```bash
source .venv/bin/activate
cd experiment/experiment
python tools/capture_build_steps.py ROBOT_IP --build tutorial
```

1. Arrange the build exactly as it should look **after step 1**, with hands clear of the build.
2. Tap and release the **front head sensor**. The tool waits briefly, restores the head pose, then saves `tutorial/step_01/reference.jpg`. The terminal confirms the saved filename.
3. Add the next placement. Tap and release again to save `step_02/reference.jpg`.
4. Repeat for all steps. Press **Ctrl+C** to stop.

Each photo must show the **entire cumulative build so far**, not just the new loose piece. The photograph is used as the expected state for that exact step. Capture the reset/empty state too if you want a separate step that verifies an empty area at the start of each activity.

Capture the other activities separately:

```bash
python tools/capture_build_steps.py ROBOT_IP --build build_1
python tools/capture_build_steps.py ROBOT_IP --build build_2
python tools/capture_build_steps.py ROBOT_IP --build build_3
```

The tool resumes at the first step without a photo. It never overwrites an existing reference. To retake one, move its old `reference.jpg` aside yourself, then use, for example:

```bash
python tools/capture_build_steps.py ROBOT_IP --build tutorial --start-step 2
```

After a retake it resumes with the next unsaved step. Every capture sets `ready` back to false for review. The head sensor takes photos **only in this separate tool**. In a participant session the head remains inactive; right foot = hold to talk/release to send, left foot = check. Foot sides are NAO's own sides, mirrored when facing it.

## Supply the expected instructions

Open each saved photo and edit its neighboring `step.json`. For example (illustrative only; write the actual instructions for your chosen build):

```json
{
  "instruction": "Place one red block across the two studs nearest me on the light-blue base.",
  "expected": "One light-blue 2x2 base on the table. One red 1x2 attached across the row nearest NAO; the other row of light-blue studs remains exposed. No other blocks in the build area.",
  "reference_photo": "reference.jpg",
  "ready": true
}
```

`instruction` is spoken directly by NAO, so write it from NAO to the participant. `expected` explains the complete state in the photo, including what matters for checking colors, counts, orientations and placements. Add those details where a photo alone could be ambiguous. Set `ready` to true only after reviewing the photo and both descriptions. You can provide these files/photos and instructions in a later change; the scaffolding is deliberately unfinished until then.

## How the check works

The session speaks only the current authored instruction. A left-foot press takes a current photo. The vision request contains **only the current step's reference**, its expected description and the live photo. It no longer uses the generated four-block illustration or the old target JSON in this mode.

- **Yes:** “Yes, that's correct! Okay, next step.” The session advances once and speaks the next authored instruction. At an activity boundary, it announces the next activity and its reset instruction. At the final step it says, “Yes, that's correct! We're all done.”
- **No:** “No, not quite yet. Let's try this step again.” It repeats the current instruction and stays on that step.
- **Uncertain:** It asks for hands to be cleared and another check. The step stays unchanged. Hidden parts are not assumed correct.
- **Capture/API/invalid-response error:** It asks to retry without advancing.

Right-foot speech is for questions about the current step. Saying “done” does not advance the workflow. Dialogue history is reset at each new step, and the current instruction is attached to questions. Step instructions and verdicts are spoken directly from code rather than rewritten by the dialogue model. Their audio is generated through the existing TTS pipeline.

## Run when all activities are ready

From `experiment/experiment`:

```bash
python tools/pregenerate_audio.py
python run_session.py --ip ROBOT_IP --pid workflow01 --condition ai
```

For rehearsing just one activity:

```bash
python run_session.py --ip ROBOT_IP --pid tutorial_test01 --condition ai --activity tutorial
```

For typed speech and checks using local current-build photos (still calls the vision API):

```bash
python run_session.py --dry-run --no-tts --pid workflow_dry01 --condition ai --activity tutorial
```

Type `/check /absolute/path/to/current_build.jpg` to check the current step, and `/end` to quit. Every new session starts at the first step; there is no automatic resume from a previous participant log. Use a fresh participant ID or `--force-new` for rehearsals. No live camera/model accuracy is implied by passing offline tests: rehearse correct, wrong, incomplete and obscured photos for each step before the participant session. A two-photo model comparison is still fallible, especially for hidden connections or visually similar pieces.

Logs record the loaded step definitions, reference-image hashes, activity/step IDs, each verdict/reason and the current camera photo. Editing a reference image during a running session invalidates the check; restart to load changes. To share captured references and metadata through Git, commit the corresponding `builds` folders and push `molly` after authoring them.

## Previous demo

The old four-block checker is preserved for comparison:

```bash
python run_session.py --ip ROBOT_IP --pid old_demo01 --condition ai --legacy-build
```

The root `MEGA_BLOKS_SETUP.md` describes that earlier demo. Its generated illustration is not used in the new step-photo workflow.
