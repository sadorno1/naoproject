# nao_project
# NAO Lego Build Guidance

A NAO robot guides a participant step by step through building a small structure out of large Lego blocks. Participants talk to the robot by holding its head sensor. They ask it to check their build by pressing its foot. The robot looks at the build with its camera, tells them what to fix, and ends the session once the structure matches the target.

The code is for a between-subjects study. Participants are told that the robot is controlled either by an **AI** or by a **human**. The robot's behavior is the same in both conditions: the same prompt, voice, gestures and timing. The condition label is only written to the session log.

## Demo video

<!-- TODO: put the video here-->

## What the code does

**Talking to the robot**
1. The participant holds the robot's **front head sensor** to speak, and the eyes turn green. The robot records audio with its microphone.
2. When the sensor is released, the recording is copied to the laptop, transcribed with OpenAI speech-to-text, and deleted. No raw audio is kept.
3. A language model writes a reply of one or two sentences. The first line of the reply picks one of seven expressions (nod, hi, listen, happy, thinking, excited, surprised), and the robot plays the matching seated animation.
4. The reply is converted to speech and played on the robot one sentence at a time, so the robot starts talking before the full reply has been generated.

**Checking the build**
1. The participant presses a **foot bumper**. The robot says "let me take a look" and takes a photo with its head camera.
2. A vision model turns the photo into structured JSON describing each block's color, size, position, layer and orientation.
3. Python code compares that description to the target structure. It reports which blocks are correct, wrong (moved, rotated, on the wrong layer, or extra) or not placed yet.
4. The language model turns the result into a spoken hint. A full match ends the session with a goodbye.

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
  inputs.py                      head-sensor and bumper handling
  session_log.py                 event logging
  prompts/                       system prompt, target structure, vision prompt, fixed lines
  tools/                         setup and analysis scripts (see below)
```

A more detailed technical README is in [`experiment/experiment/README.md`](experiment/experiment/README.md).

## How to run

### 1. Requirements

- A NAO robot on the same network as the laptop (you need its IP address)
- Python 3.12
- An OpenAI API key

### 2. Install

```bash
git clone <this repo>
cd nao_project
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
# optional, only if TRANSCRIBE_BACKEND = "faster-whisper" in config.py:
pip install -r experiment/experiment/requirements-local-stt.txt
```

Create a file `experiment/.env` (the folder **above** the code folder) containing:

```
OPENAI_API_KEY=sk-...
```

### 3. One-time setup on the robot

Run these from `experiment/experiment/`:

```bash
python tools/sensor_probe.py <robot-ip>         # check the head sensor and bumper names match config.py
python tools/camera_probe.py <robot-ip> --set-head   # frame the build area, adjust HEAD_PITCH in config.py
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

- The robot sits down, greets the participant and gives the first step. After that, it responds to head-sensor speech and bumper presses.
- Press **`q`** in the terminal to end a session early.
- Data is saved to `data/<pid>/`. The script refuses to reuse an existing participant ID unless you pass `--force-new`.

### 5. Test without a robot (dry run)

```bash
python run_session.py --dry-run --pid test01 --condition ai --image test_photos/correct/<photo>.jpg [--no-tts]
```

Type what the participant would say. Type `/check` to simulate a bumper press and `/end` to stop. The OpenAI API is still called.

### 6. Summarize logs

```bash
python tools/summarize_log.py data --csv summary.csv
```

This gives per-session counts: bumper presses, robot instructions, repeated instructions, identity questions ("are you an AI?"), completion time and median latencies.
