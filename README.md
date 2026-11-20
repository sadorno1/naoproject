# NAO Mega Bloks Build Guidance

A NAO robot guides a participant step by step through building a small structure out of Mega Bloks. Participants talk to the robot by holding its right foot bumper. They ask it to check their build by pressing its left foot bumper. The robot looks at the build with its camera, tells them what to fix, and ends the session once the structure matches the target.

The code is for a between-subjects study. Participants are told that the robot is controlled either by an **AI** or by a **human**. The robot's behavior is the same in both conditions: the same prompt, voice, gestures and timing. The condition label is only written to the session log.

The default workflow is now **tutorial → build 1 → build 2 → build 3**. The tutorial is a ready-to-use walkthrough of right-foot talking and left-foot checks, with no head control or reference photos. The three builds use authored instructions, expected descriptions and robot reference photos for each step. See [BUILD_WORKFLOW.md](BUILD_WORKFLOW.md) for the folder structure, author-only head-tap photo capture and run commands. The three build templates are intentionally blank until you supply the photos and instructions; full sessions will not start with unfinished builds. You can run the controls tutorial alone with `--activity tutorial`.

The earlier two-layer, four-block wall is retained with `--legacy-build`; see [MEGA_BLOKS_SETUP.md](MEGA_BLOKS_SETUP.md) for that demo. Older single-build examples below need `--legacy-build` until the new workflow is authored.

## Demo video

<!-- TODO: put the video here-->

## What the code does

**Talking to the robot**
1. The participant holds the robot's **right foot bumper** to speak, and the eyes turn green. The robot records audio with its microphone.
2. When the sensor is released, the recording is copied to the laptop, transcribed with OpenAI speech-to-text, and deleted. No raw audio is kept.
3. A language model writes a reply of one or two sentences. The first line of the reply picks an expression label. Physical gestures are disabled by default for calm motion; optional gestures are spaced apart and cannot overlap.
4. The reply is converted to speech and played on the robot one sentence at a time, so the robot starts talking before the full reply has been generated.

**Checking the build**
1. The participant presses a **left foot bumper**. The robot says "let me take a look" and takes a photo with its head camera.
2. A vision model compares the live photo with the current step's robot reference photo and your expected-state description, returning yes, no or uncertain.
3. On yes, the chatbot offers encouragement, code advances once, and NAO speaks the next authored instruction. Completing an activity gets a celebration and an invitation to the next build. On no, NAO gives a short hint and repeats the current instruction. No, uncertainty and failed checks keep the current step.
4. After the tutorial and all three builds pass their final checks, the session ends. The old coordinate-based checker is used only with `--legacy-build`.

**Logging:** Every session writes a timestamped event log (`.jsonl`) with transcripts, robot utterances, gestures, sensor presses, build-check results, per-stage latencies and completion time. The log also stores hashes of the prompt files, which confirm that both conditions used identical prompts.

### Models and versions

| Component | Used |
|---|---|
| Robot | NAO, NAOqi 2.1.4.13, seated |
| Robot SDK | `qi` 3.1.5 (Python) |
| Dialogue | OpenAI `gpt-4.1-mini` (streamed, max 200 tokens) |
| Vision | OpenAI `gpt-4.1` with JSON-schema structured output |
| Speech-to-text | OpenAI `gpt-4o-mini-transcribe` (alternatives: `whisper-1`, or local `faster-whisper`) |
| Text-to-speech | OpenAI `tts-1`, voice `sage` |
| Laptop | Python 3.12 |

All settings are in `experiment/experiment/config.py`.

## Repository layout

```
requirements.txt                 Python dependencies
experiment/experiment/
  run_session.py                 entry point: runs one participant session
  config.py                      all settings (models, sensors, posture, volume, camera, ...)
  dialogue.py                    language-model conversation and streaming
  speech.py                      text-to-speech and playback on the robot
  transcribe.py                  speech-to-text
  vision.py                      photo -> block JSON -> comparison with the target
  nao_proxy.py                   wrapper around the NAOqi services (LEDs, motion, camera, audio)
  robot_link.py                  SSH/SFTP file transfer to and from the robot
  inputs.py                      right-foot talk and left-foot check handling
  session_log.py                 event logging
  prompts/                       system prompt, target structure, vision prompt, fixed lines
  tools/                         setup and analysis scripts (see below)
```


## How to run

### 1. Requirements

- A NAO robot on the same network as the laptop (you need its IP address)
- Python 3.12
- An OpenAI API key

### 2. Install

```bash
git clone --branch molly https://github.com/sadorno1/naoproject.git
cd naoproject
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
# optional, only if TRANSCRIBE_BACKEND = "faster-whisper" in config.py:
pip install -r experiment/experiment/requirements-local-stt.txt
```

From the repository root, run the key setup helper:

```bash
python setup_keys.py
```

Paste your OpenAI API key at the hidden prompt. This one key is used for dialogue, photo checks, speech generation and cloud transcription. The helper saves it to `experiment/.env`, preserves unrelated settings, and never prints the key. The file and temporary save files are ignored by Git; on Linux it is written with owner-only permissions. The key is stored as local text, not encrypted. Rerun the command to replace it; Enter without a key leaves the setup unchanged. No paid API request is made by setup, so it does not validate the key with OpenAI.

Manual alternative: copy `experiment/.env.example` to `experiment/.env` and fill in `OPENAI_API_KEY` there. Do not put a real key in the example file. An `OPENAI_API_KEY` already exported in the terminal takes priority over this file; run `unset OPENAI_API_KEY` on Linux if you want to use the saved key instead. Restart a running session after changing the key.

### 3. One-time setup on the robot

Run these from `experiment/experiment/`:

```bash
python tools/sensor_probe.py <robot-ip>         # check the right talk and left check bumper names match config.py
python tools/camera_probe.py <robot-ip> --set-head --camera 0 --out tmp/camera_top
python tools/camera_probe.py <robot-ip> --set-head --camera 1 --out tmp/camera_bottom
python tools/gesture_probe.py <robot-ip> --list-all  # check the seated animations exist
python tools/bench_models.py                    # check the OpenAI models work and measure latency
python tools/pregenerate_audio.py               # cache the greeting / "take a look" / goodbye audio
```

To change the target structure, edit `prompts/target_description.txt` (in words, from the participant's view) and `prompts/target_structure.json` (as blocks, from the camera's view). Then run `pregenerate_audio.py` again.

### 4. Run a session

```bash
cd experiment/experiment
python run_session.py --ip <robot-ip> --pid P01 --condition ai      # or --condition human
```

- The robot sits down, greets the participant and gives the first step. After that, it responds to right-bumper speech and left-bumper check presses.
- Press **`q`** in the terminal to end a session early.
- Data is saved to `data/<pid>/`. The script refuses to reuse an existing participant ID unless you pass `--force-new`.

### 5. Test the update

**Offline regression tests** — run from the repository root. These need only Pillow, and do not need a robot or API key:

```powershell
python -m pip install Pillow
python -m unittest discover -s experiment/experiment/tests -v
```

The offline tests cover the four-piece wall inventory, missing and rotated pieces, blue versus light blue, unclear camera views, gesture overlap, head positioning, and restoration of movement settings. Passing these tests does not establish camera accuracy or physical motion quality.

**Camera framing** — after installing the full requirements, run from `experiment/experiment`. Replace `ROBOT_IP` with NAO's IP address:

```powershell
python tools/camera_probe.py ROBOT_IP --set-head --camera 0 --out tmp/camera_top
python tools/camera_probe.py ROBOT_IP --set-head --camera 1 --out tmp/camera_bottom
```

Open the saved JPEGs and choose the camera that shows the entire wall, studs, and block seams. Save that camera number in `CAMERA_INDEX` in `config.py`. If neither view works, adjust the build location or try `--pitch 0.45`, then save the successful `HEAD_PITCH` and `HEAD_YAW` too. Probe options preview settings without saving them. See [MEGA_BLOKS_SETUP.md](MEGA_BLOKS_SETUP.md) for the target layout and more camera guidance.

**Vision and dialogue without the robot** — provide an actual photo of your pieces, not an empty placeholder path. The full requirements and `experiment/.env` API key are needed. From `experiment/experiment`:

```powershell
python run_session.py --dry-run --no-tts --pid wall_dry01 --condition ai --image "C:/path/to/your/wall.jpg" --force-new
```

Type `/check` to assess the photo, normal text to talk to NAO, and `/end` to stop. The OpenAI API is still called; `--no-tts` skips speech generation. `--force-new` creates a fresh timestamped data folder if the test ID was already used.

**Full robot test** — from `experiment/experiment`, after saving the camera settings and setting the API key:

```powershell
python tools/sensor_probe.py ROBOT_IP
python tools/pregenerate_audio.py
python run_session.py --ip ROBOT_IP --pid wall_robot01 --condition ai --force-new
```

The sensor probe stays running to show touch events; press Ctrl+C after testing both foot bumpers, then run the next two commands. During a session, hold NAO's right foot bumper to speak and release it to send speech. Press NAO's left foot bumper to check the build; press `q` in the terminal to stop. Test an empty view, a partial wall, a deliberately misplaced piece, and the finished wall. Confirm calm motion and that unclear/hidden pieces do not lead to a false success. Photos and check results are saved under `data/` for review.

### 6. Summarize logs

```bash
python tools/summarize_log.py data --csv summary.csv
```

This gives per-session counts: bumper presses, robot instructions, repeated instructions, identity questions ("are you an AI?"), completion time and median latencies.
