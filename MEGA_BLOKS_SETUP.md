# Mega Bloks pillar update

This version recognizes your pieces: two light-blue 2x2s, four red 1x2s, and two blue 1x4s. Sizes count the large studs. Blue and light blue are separate colors. All dialogue, the greeting, and the camera prompt now use Mega Bloks terminology.

## Pillar

Build from the bottom up. Each row below is a complete layer; NAO gives one piece placement at a time.

| Layer | Pieces | Placement |
|---|---|---|
| 5, top | Two red 1x2s | Side by side, making a 2x2 top |
| 4 | One light-blue 2x2 | Centered on the blue middle |
| 3 | Two blue 1x4s | Side by side, centered, making a 4x2 middle with one stud overhanging at each end |
| 2 | Two red 1x2s | Side by side, covering the base |
| 1, bottom | One light-blue 2x2 | Flat on the table |

The top and bottom have a 2x2 footprint. The wider blue middle is centered. All long pieces run left to right. The written instructions and camera target describe the same arrangement. Every piece must be verified before completion; if a rear piece is hidden, NAO should request a clearer view. A single camera cannot confirm fully hidden pieces.

## Check what NAO actually sees first

From `experiment/experiment`, replace `ROBOT_IP` below with your robot's IP address:

```powershell
python tools/camera_probe.py ROBOT_IP --set-head --camera 0 --out tmp/camera_top
python tools/camera_probe.py ROBOT_IP --set-head --camera 1 --out tmp/camera_bottom
```

Open the JPEGs in those folders. Put a light-blue piece on the marked build spot, then test the full pillar. The whole pillar and the tops of the pieces should be in frame. Move the build spot farther from or closer to NAO as needed, clear hands away, and use even lighting. The tool checks photo capture and video fallback separately; a successful capture alone does not prove that blocks are in view.

If needed, try another downward angle, for example:

```powershell
python tools/camera_probe.py ROBOT_IP --set-head --camera 1 --pitch 0.45 --out tmp/camera_bottom_down
```

Save the successful `CAMERA_INDEX`, `HEAD_PITCH`, and `HEAD_YAW` values in `config.py`. The probe only previews these values; it does not save them. The default remains the top camera because the robot's physical setup has not been measured here. Use the saved probe image to confirm framing before running a participant session. Raw and model-input photos from session checks are also saved in the participant data folder for diagnosis.

Optional: set `REFERENCE_PHOTO_PATH` in `config.py` to a photo of the finished pillar taken with that same camera and pose. It supplies examples of the pieces and lighting; it is not treated as evidence of the current build.

## Movement changes

- Physical expression animations are off by default (`GESTURES_ENABLED = False`). Speech and eye feedback still work.
- Posture changes use a lower speed. Head movements use a slow blocking interpolation and a settling pause before photos.
- Every real camera check restores the configured head pose, including when no look gesture is configured.
- Background and listening movements and basic awareness are temporarily paused when the NAOqi 2.1 services support it. Original settings are restored when the session exits. Unavailable services are reported in the terminal.
- If gestures are enabled later, a cooldown and overlap guard space them apart. The camera waits for them and defers its check if movement does not stop. The gesture probe's `--play` option explicitly previews animations even while session gestures are disabled.

The blocking head movement follows [Aldebaran's joint-control API](https://doc.aldebaran.com/2-1/naoqi/motion/control-joint-api.html). No physical robot was connected during development, so movement speed and camera framing need verification on your NAO.

## Run

Use the existing Python environment and API key setup described in the README. No new runtime dependencies were added. Rebuild cached fixed audio after the greeting change:

```powershell
python tools/pregenerate_audio.py
python run_session.py --ip ROBOT_IP --pid P01 --condition ai
```

Press a foot bumper to check the build. Vision still runs on demand, rather than continuously. Checks preserve more image detail, distinguish your three footprints and two shades of blue, and ask for a clearer view if the frame is unclear or no blocks are seen. Uncertain extra blocks prevent a success result.

## Offline verification

From the repository root, with Pillow installed:

```powershell
python -m unittest discover -s experiment/experiment/tests -v
```

The regression suite covers the eight-piece inventory, correct and incorrect pillar observations, missing/hidden/uncertain pieces, blank frames, light-blue versus blue, photo paths, head positioning, gesture overlap/cooldown, and restoration of autonomous movement settings. These tests use simulated observations and robot services. They do not measure actual image-recognition accuracy or physical motion.
