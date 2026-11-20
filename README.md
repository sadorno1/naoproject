# NAO Mega Bloks Build Guidance

NAO guides a participant through a tutorial and three Mega Bloks builds. The tutorial teaches the controls and includes a mini build. Each construction step is checked against a reference photo taken on the robot and an expected-state description supplied by the experimenter.

Development is currently on the **`molly` branch**. The authored activities now contain **19 steps and 17 reference photos**: two control exercises, three tutorial placements, four build-1 placements, and five placements each for builds 2 and 3. All step files and photo paths pass offline validation. Camera accuracy and spoken instructions still need rehearsal on NAO.

## Quick start: take photos for upload

From your Linux repository folder:

```bash
git switch molly
git pull --ff-only origin molly
source .venv/bin/activate
cd experiment/experiment
python run_session.py --photo-mode --ip ROBOT_IP
```

Replace `ROBOT_IP` with NAO's IP address. **Tap and release the front head sensor** to save each numbered photo. **Press Ctrl+C** when finished; the program prints the path to a ZIP containing all saved photos and their capture details. Upload that ZIP to share the collection at once. Originals are kept in `photo_sessions/` too.

Photo-only mode needs no API key, participant ID or completed build setup. It does not run the chatbot or upload anything automatically. Keep track of which photo numbers belong to each tutorial/build step; the photos are not assigned or approved as references automatically. Run this mode separately from the participant session. For a custom output parent, add `--photo-dir ~/nao_photos`.

## Participant flow

```text
Greeting
  -> Practice talking with the left foot bumper
  -> Practice requesting a check with the right foot bumper
  -> Tutorial mini build, checked after each placement
  -> Celebrate finishing the tutorial
  -> Build 1 -> celebrate -> Build 2 -> celebrate -> Build 3
  -> Final celebration and session end
```

1. **Talk practice:** hold NAO's left bumper, say hello, then release. Its eyes turn green during recording. Understandable speech advances the tutorial; an empty recording does not.
2. **Check practice:** press NAO's right bumper once. A successful camera capture completes this exercise, without judging a build. Pressing it before completing talk practice gives a reminder.
3. **Tutorial mini build:** follow the three authored placements at `tutorial/step_03` through `step_05`. Each placement needs a successful photo comparison; change the number of placements in `tutorial/build.json` if needed.
4. **Three main builds:** finish each build one checked step at a time. NAO celebrates completing an activity, introduces the next one, and gives its starting/reset instruction.

## Participant controls

| Control | Action |
|---|---|
| Hold the bumper on the foot labeled **TALK** | Record speech; eyes turn green |
| Release the TALK bumper | Send the recording for transcription |
| Press the bumper on the foot labeled **CHECK** | Request a camera check |
| Head sensor | Inactive during the participant session |
| `q` in the terminal | Experimenter ends the session |

For setup, put **TALK on NAO's left foot** and **CHECK on NAO's right foot** (NAO's own sides). Spoken instructions refer to the labels instead of foot sides. Left/right still applies normally to block-placement instructions. Short accidental talk holds are discarded. Inputs are ignored while busy by default. Head tapping is used only in a separate experimenter reference-photo tool; it is never taught to participants or enabled in their session.

## How a construction check works

For the current step, the vision model receives your reference photo, your expected-state description, and NAO's latest participant-build photo. It returns **yes**, **no**, or **uncertain**.

| Result | NAO's response | Progress |
|---|---|---|
| Correct | Short chatbot-generated encouragement | Give the next authored instruction |
| Activity finished | Celebrate, then invite the next activity | Begin its starting/reset instruction |
| Wrong | Give a short hint, then repeat the exact instruction | Stay on the current step |
| Unclear photo | Ask for hands to be cleared and another check | Stay on the current step |
| Capture/API failure | Ask to retry | Stay on the current step |

The session controls progression in code. During construction, saying “done” does not pass a step. Left-bumper speech lets participants ask questions about the current instruction. Dialogue history resets at each new step. Hints use the expected state and observed mismatch, or your optional authored `hint`. Generated feedback has fallback wording if its text-generation request fails.

Spoken instructions omit internal step numbers and activity titles. The greeting and transitions use conversational wording. Placement praise is capped at six words, celebrations at fifteen, and retry hints at twenty-five; longer or label-reading feedback falls back to a short prepared response. Step numbers and titles remain in the files/logs for tracking.

The final successful check celebrates and ends the session. There is no additional build after build 3. The new workflow does not use the old generated top-view illustration or coordinate target JSON.

## Install or update on Linux

For a new checkout:

```bash
git clone --branch molly https://github.com/sadorno1/naoproject.git
cd naoproject
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Use a Python environment compatible with the pinned NAOqi `qi` package; the project was set up for Python 3.12. NAO and the computer must be able to communicate over the network, including SSH/SFTP file transfer. The configured robot posture is seated.

For an existing checkout, from its root:

```bash
git switch molly
git pull --ff-only origin molly
source .venv/bin/activate
```

Optional local transcription, only if you select `faster-whisper` in `config.py`:

```bash
python -m pip install -r experiment/experiment/requirements-local-stt.txt
```

## Configure the API key

From the repository root:

```bash
python setup_keys.py
```

Paste the OpenAI API key at the hidden prompt. One key is used for dialogue, feedback, vision, generated speech and cloud transcription. It is saved in `experiment/.env`, which Git ignores. The helper preserves unrelated settings, never prints the key and writes owner-only permissions on Linux. It stores local text, not encrypted data, and makes no API request to validate the key. Rerun it to replace the key; Enter leaves the setup unchanged.

Manual alternative: copy `experiment/.env.example` to `experiment/.env` and fill in `OPENAI_API_KEY` there. An already exported `OPENAI_API_KEY` takes priority; use `unset OPENAI_API_KEY` on Linux to use the file instead. Restart running sessions after changing the key.

## Check the sensors and camera

From the repository root:

```bash
cd experiment/experiment
python tools/sensor_probe.py ROBOT_IP
```

Replace `ROBOT_IP` with NAO's IP address. Check left-bumper hold/release and right-bumper press events, then stop the sensor probe with Ctrl+C.

```bash
python tools/camera_probe.py ROBOT_IP --set-head --camera 0 --out tmp/camera_top
python tools/camera_probe.py ROBOT_IP --set-head --camera 1 --out tmp/camera_bottom
```

Open the saved images. Choose a view that shows the entire build, large studs and seams. Save the chosen `CAMERA_INDEX`, `HEAD_PITCH`, `HEAD_YAW` and capture method in `config.py`; the probe only previews settings. Keep posture, build spot and lighting consistent for references and participant checks.

## Quick photo-only mode: collect everything for upload

From `experiment/experiment`:

```bash
python run_session.py --photo-mode --ip ROBOT_IP
```

This starts only the robot camera and the front head sensor. No API key, participant ID, condition, completed build files, conversation or speech generation is needed. Arrange each build state, clear hands, then **tap and release the front head sensor** to save `photo_001.jpg`, `photo_002.jpg`, and so on. A short settling delay lets the head return to its configured pose. Bumpers are inactive in this mode. Do not run it alongside a participant session or another camera tool.

Press **Ctrl+C** when all photos are taken. A ZIP containing every saved photo and a `manifest.json` with capture settings/timestamps is created, and its full path is printed. Upload that ZIP manually to share the whole collection at once. Original photos are retained too. Each run creates a separate timestamped folder and ZIP under `experiment/experiment/photo_sessions/`, which is Git-ignored. Nothing is uploaded automatically.

To choose a different output parent folder:

```bash
python run_session.py --photo-mode --ip ROBOT_IP --photo-dir ~/nao_photos
```

These are unassigned photos: they do not automatically become approved step references. Keep track of which numbered images belong to the tutorial and each build, so they can be placed beside the correct step instructions afterward. To capture directly into the step folders instead, use the authoring tool below. Head tapping remains absent from participant sessions.

## Prepare the mini build and three main builds

From `experiment/experiment`, run the author-only capture tool for each activity:

```bash
python tools/capture_build_steps.py ROBOT_IP --build tutorial
python tools/capture_build_steps.py ROBOT_IP --build build_1
python tools/capture_build_steps.py ROBOT_IP --build build_2
python tools/capture_build_steps.py ROBOT_IP --build build_3
```

Run one at a time, separately from the participant session. Arrange the cumulative build state after a placement, clear hands, then tap and release the front head sensor. The tool saves a numbered photo after settling. The tutorial automatically skips its two control exercises and starts at `step_03`; main builds start at `step_01`. Ctrl+C stops capture. Existing photos are never overwritten.

For each construction step, edit `step.json` with:

- `instruction`: the exact instruction NAO should say to the participant.
- `expected`: the full expected state after this placement.
- `hint`: an optional preferred hint for an incorrect check.
- `reference_photo`: the saved reference filename.
- `ready`: set to `true` after reviewing the photo and text.

Each activity's `build.json` lists its steps in order. The tutorial's first two steps have `completion` values `talk` and `check`; later steps are photo-checked placements. The tutorial is not complete until its mini build passes.

See [BUILD_WORKFLOW.md](BUILD_WORKFLOW.md) for the full structure, examples and retake instructions. Full sessions validate every activity before starting; `--activity tutorial` validates only the tutorial. Draft placements or missing photos prevent startup.

## Cache audio and run

From `experiment/experiment`, after the steps are ready:

```bash
python tools/validate_builds.py
python tools/pregenerate_audio.py
python run_session.py --ip ROBOT_IP --pid P01 --condition ai
```

Validation checks shared phrases, ordered step definitions, approvals and readable reference photos without a robot or API key. Shared greetings/check phrases are stored in `experiment/experiment/fixed_lines.json`. The current workflow has no dependency on the deleted `prompts/` folder; archived text under `legacy_prompts/` is used only for the old checker.

The cache tool prepares fixed phrases and instructions for ready activities. Unfinished activities are reported and skipped for caching. Encouragement, celebrations and hints are generated during the session. Speech uses the configured voice with bounded WAV gain adjustment to boost quiet audio before upload. Hardware `VOLUME` is a separate setting.

To rehearse only the tutorial, once its mini-build photos and instructions are ready:

```bash
python run_session.py --ip ROBOT_IP --pid tutorial_test01 --condition ai --activity tutorial
```

Use `--activity build_1`, `build_2` or `build_3` to rehearse one main build. Use a new participant ID for each session or pass `--force-new` to create a timestamped subfolder. Sessions start at the first selected step; they do not resume progress automatically. Press `q` to end early.

If you end an unfinished session with `q`, NAO says: “Aw, it looks like we're out of time! Thank you for building with me. I had a lot of fun!” This is the editable `early_goodbye` phrase in `fixed_lines.json`. It is cached at startup and by `tools/pregenerate_audio.py`. Normal completion keeps the generated celebration. On Linux's line-based terminal reader, type `q` then Enter; in dry run use `/end`.

The study condition can be `ai` or `human`. It is logged only; it does not choose a different implementation, prompt or voice.

### Dry run without the robot

From `experiment/experiment`, with the selected activity's photos and instructions ready:

```bash
python run_session.py --dry-run --no-tts --pid dry01 --condition ai --activity tutorial
```

Type a sentence to simulate speech, `/check /absolute/path/to/current_build.jpg` to simulate a check, and `/end` to stop. Supply the appropriate current photo for each placement. API calls are still made for dialogue, feedback and construction checks; `--no-tts` disables speech synthesis. The tutorial's initial camera-control exercise verifies capture only, without a vision comparison.

## Tests and live rehearsal

From the repository root, offline tests need Pillow but no robot or API key:

```bash
python -m pip install Pillow
python -m unittest discover -s experiment/experiment/tests -v
```

Tests cover controls, tutorial progression, photo-step advancement, retry behavior, reference handling, feedback, audio processing and key setup, plus the earlier checker. Passing them does not establish live camera accuracy, useful model-generated hints, physical motion or speaker loudness. Rehearse correct, incorrect, incomplete and obscured builds at each step on NAO before a participant session.

## Files and logs

| File or folder | Purpose |
|---|---|
| `setup_keys.py` | Hidden-input API key setup |
| `experiment/experiment/config.py` | Models, controls, camera, posture and audio settings |
| `experiment/experiment/builds/` | Tutorial and three builds, with step instructions and references |
| `build_workflow.py` | Validate activities and track the current step |
| `run_session.py` | Participant-session controller |
| `step_vision.py` | Compare a step reference with the current build photo |
| `workflow_feedback.py` | Generate encouragement, celebrations and hints |
| `dialogue.py` | Answer questions about the current step |
| `speech.py`, `audio_levels.py` | Speech generation, bounded gain and playback |
| `reference_capture.py`, `tools/capture_build_steps.py` | Author-only reference-photo capture |
| `inputs.py`, `nao_proxy.py`, `robot_link.py` | Controls, NAO services and file transfer |
| `vision.py`, target prompt files | Earlier single-build checker |

Except where a full path is shown, implementation filenames in the table are under `experiment/experiment`.

Session data is saved under `experiment/experiment/data/<pid>/`. Logs include transcripts, robot speech, sensor events, step definitions, reference hashes, check verdicts/reasons, generated feedback and completion. Current check photos are retained. Raw microphone recordings are deleted after transcription. Data, cached audio, scratch files and API-key files are excluded from Git; reference photos under `builds/` can be committed deliberately.

`tools/summarize_log.py` provides existing per-session summaries; inspect the JSONL `step_check_result`, `workflow_feedback` and `tutorial_control_passed` events for the new workflow details. The earlier `tools/eval_vision.py` evaluates the legacy coordinate checker, not the new per-step photo comparisons.

## Earlier four-block demo

The old single-build workflow remains available from `experiment/experiment`:

```bash
python run_session.py --ip ROBOT_IP --pid old_demo01 --condition ai --legacy-build
```

See [MEGA_BLOKS_SETUP.md](MEGA_BLOKS_SETUP.md) for that demo. Its coordinate target and text assets are archived under `legacy_prompts/`. The deleted generated illustration is not restored; `REFERENCE_PHOTO_PATH` defaults to `None`. None of these old targets are sent to the current step-photo checker.
