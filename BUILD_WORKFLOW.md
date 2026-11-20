# Tutorial and three builds

The default session runs **tutorial → build 1 → build 2 → build 3**, in that order. The tutorial combines a two-step controls walkthrough with a photo-checked mini build; each main build can also have as many photo-checked steps as you need. The old four-block demo remains available with `--legacy-build`.

## Participant tutorial

The tutorial teaches how to use NAO, then lets the participant practice those controls on a mini build:

1. **Practice talking.** NAO explains its own left/right foot sides, the green recording eyes, and holding the right bumper while speaking, then releasing it. The participant says hello. An understandable recording completes this practice step. Empty/unrecognized speech stays here, and pressing the left bumper early gives a reminder rather than skipping ahead.
2. **Practice asking for a check.** NAO explains pressing the left bumper once, and clearing hands from the build area. A successful practice photo completes this control exercise; there is no target photo or build-correctness judgment yet. A capture failure asks for another try.
3. **Practice a mini build.** Starting at `step_03`, NAO gives your authored placement instructions. Each step compares the participant's photo against your reference and expected description, just like the main builds. A correct check advances; an incorrect check gives a hint and repeats the instruction; uncertainty asks for another photo. Saying “done” does not pass a placement.

NAO encourages the participant during practice, then celebrates finishing the tutorial only after the mini build's final photo passes. It then introduces build 1. The tutorial uses `mode: "controls_and_build"`: the first two `step.json` files have editable spoken instructions and `completion` values (`talk`, then `check`), with no photos or `ready` flags. All later tutorial steps are photo-checked placements and require instructions, expected descriptions, approved reference photos and `ready: true`. Two draft mini-build slots (`step_03` and `step_04`) are provided. Add/remove placement steps in the tutorial's ordered `steps` list as needed, keeping at least one after the two controls. `mini_build_intro` supplies the transition into the mini build.

You can run the tutorial alone with `--activity tutorial` once its mini build is authored, even while all three main builds are still drafts. In dry run, a typed sentence simulates speech and `/check /path/to/photo.jpg` simulates the camera capture or checks the current mini-build placement.

**The participant tutorial and final session do not use the head sensor.** Head tapping is an author-only reference-capture tool, run separately before the participant session. Do not run that tool alongside the final session.

## Where your material goes

```text
experiment/experiment/builds/
  tutorial/
    build.json
    step_01/
      step.json           # right-bumper talking practice
    step_02/
      step.json           # left-bumper check practice
    step_03/
      step.json           # first mini-build placement, draft
      reference.jpg       # capture with the authoring tool
    step_04/
      step.json           # second mini-build placement, draft
      reference.jpg
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

The tutorial is supplied with controls instructions and two draft mini-build placement slots. The three main builds start with a blank, unapproved first step. No build designs or expected photos have been invented. You supply those photos and expected states. A full session refuses to start until the tutorial mini build and all three main builds have reviewed photo steps, nonempty instructions, expected descriptions, and readable reference photos. Captured photo steps store `reference.jpg` and `capture.json` beside their `step.json`.

`build.json` contains a title, a spoken `start_instruction` (such as clearing the build area), and the ordered `steps` list. Every listed step is required. The tool appends newly captured steps to this list in numeric order. Edit the list if you want a different order or remove an unused step. Do not remove a step whose placement is required by a later reference unless you also update the instructions.

## Capture reference photos by tapping the head

If you want to take an unassigned collection and upload all photos together before arranging the step files, use `python run_session.py --photo-mode --ip ROBOT_IP` from `experiment/experiment`. Tap/release the head sensor for each photo and press Ctrl+C when finished. This creates a numbered collection and an upload ZIP under `photo_sessions/` and prints the ZIP path. It needs no API key or authored steps. It does not assign or approve references automatically. The instructions below are for capturing directly into named activity/step folders instead.

Stop any running participant session first. Use the same robot posture, build spot, camera and head pose you plan to use during the session; set these in `config.py`. This tool uses those settings and restores background movement on exit. Camera/head/posture metadata is checked at session startup when available. Physical build placement and lighting still need a visual check.

On Linux, from the repository root:

```bash
source .venv/bin/activate
cd experiment/experiment
python tools/capture_build_steps.py ROBOT_IP --build build_1
```

1. Arrange the build exactly as it should look **after step 1**, with hands clear of the build.
2. Tap and release the **front head sensor**. The tool waits briefly, restores the head pose, then saves `build_1/step_01/reference.jpg`. The terminal confirms the saved filename.
3. Add the next placement. Tap and release again to save `step_02/reference.jpg`.
4. Repeat for all steps. Press **Ctrl+C** to stop.

Each photo must show the **entire cumulative build so far**, not just the new loose piece. The photograph is used as the expected state for that exact step. Capture the reset/empty state too if you want a separate step that verifies an empty area at the start of each activity.

Capture each build separately. The tutorial command automatically skips the first two control exercises and starts at `step_03`:

```bash
python tools/capture_build_steps.py ROBOT_IP --build tutorial
python tools/capture_build_steps.py ROBOT_IP --build build_1
python tools/capture_build_steps.py ROBOT_IP --build build_2
python tools/capture_build_steps.py ROBOT_IP --build build_3
```

The tool resumes at the first step without a photo. It never overwrites an existing reference. To retake one, move its old `reference.jpg` aside yourself, then use, for example:

```bash
python tools/capture_build_steps.py ROBOT_IP --build build_1 --start-step 2
```

After a retake it resumes with the next unsaved step. Every capture sets `ready` back to false for review. The head sensor takes photos **only in this separate tool**. In a participant session the head remains inactive; right foot = hold to talk/release to send, left foot = check. Foot sides are NAO's own sides, mirrored when facing it.

## Supply the expected instructions

Open each saved photo and edit its neighboring `step.json`. For example (illustrative only; write the actual instructions for your chosen build):

```json
{
  "instruction": "Place one red block across the two studs nearest me on the light-blue base.",
  "expected": "One light-blue 2x2 base on the table. One red 1x2 attached across the row nearest NAO; the other row of light-blue studs remains exposed. No other blocks in the build area.",
  "hint": "Check which row of the light-blue base the red block is attached to.",
  "reference_photo": "reference.jpg",
  "ready": true
}
```

`instruction` is spoken directly by NAO, so write it from NAO to the participant. `expected` explains the complete state in the photo, including what matters for checking colors, counts, orientations and placements. Add those details where a photo alone could be ambiguous. The optional `hint` supplies a preferred hint after an incorrect check; without one, the chatbot uses the expected state and observed mismatch to suggest a brief hint. Set `ready` to true only after reviewing the photo and descriptions. You can provide these files/photos and instructions in a later change; the scaffolding is deliberately unfinished until then.

## How the check works

During the tutorial mini build and the three main builds, the session speaks only the current authored instruction. A left-foot press takes a current photo. The vision request contains **only the current step's reference**, its expected description and the live photo. It no longer uses the generated four-block illustration or the old target JSON in this mode. Only the first two tutorial control exercises use practiced interactions instead of this comparison.

- **Yes, mid-build:** The chatbot generates a brief, encouraging confirmation. The session advances once and speaks the next authored instruction.
- **Yes, activity finished:** The chatbot celebrates finishing the tutorial or build, then invites the participant to the next named activity. The session announces that activity, its reset instruction and its first step. After the final build (or the final step of a single-activity rehearsal), it celebrates and ends without inventing another build.
- **No:** The chatbot gently offers a short hint grounded in the authored hint or the expected state and observed mismatch. NAO then repeats the exact current instruction and stays on that step. It does not repeat the activity's reset/clear instruction during a retry.
- **Uncertain:** It asks for hands to be cleared and another check. The step stays unchanged. Hidden parts are not assumed correct.
- **Capture/API/invalid-response error:** It asks to retry without advancing.

During the three builds, right-foot speech is for questions about the current step; saying “done” does not advance a build. The tutorial's talking practice instead advances on an understandable recording, as described above. Dialogue history is reset at each new step, and the current instruction is attached to questions. The chatbot chooses social feedback and hints, but code controls progression and speaks the exact authored instructions. Feedback is limited to one or two short sentences; its prompt forbids invented placements and future steps. If feedback generation fails, a fallback confirmation or hint is used. An additional text-generation request is made per correct/incorrect check or successful tutorial practice. Feedback text, its type and fallback status are logged. All speech uses the existing TTS pipeline. Live wording and hint usefulness still need rehearsal.

## Run when all activities are ready

If your API key is not configured, run `python setup_keys.py` from the repository root first. Paste the key at the hidden prompt; the helper saves it locally in the Git-ignored `experiment/.env`. All OpenAI features use that same key.

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
