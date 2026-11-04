# Four-block demo

Use exactly two light-blue 2x2 pieces and two red 1x2 pieces. Put the other pieces away, outside the camera view. Sizes count the large Mega Bloks studs.

## Shape and sketch

Front view from NAO (widths are in studs):

```text
       +---------+---------+
       | RED 1x2 | RED 1x2 |   upper layer
       +---------+---------+
       |  LIGHT  |  LIGHT |
       |BLUE 2x2 |BLUE 2x2|   bases resting on the table
       +---------+---------+
```

Top view (each letter is one stud):

```text
                 NAO / CAMERA
                 "NAO SIDE"
                  R R | R R    red blocks on top of bases
                  L L | L L    exposed light-blue base studs
                  participant
```

The bases touch, making a 4x2 footprint. Each red block covers the two studs nearest NAO on one base. Both red blocks run left to right, with no overhangs. For a participant sitting opposite NAO, the red row is the row farthest from them. Mark the table edge nearest NAO with a small "NAO SIDE" label. Keep `PARTICIPANT_SIDE = "facing"` for this setup.

## Four placements

1. Place one light-blue base on the marked spot.
2. Place the other light-blue base directly beside it, edges touching and rows aligned.
3. Put one red block across the NAO SIDE row of either base.
4. Put the other red block across the NAO SIDE row of the remaining base.

Ask for a bumper check after each placement. Either base and either red may be placed first. A single base has no unique left/right identity, so the checker may report an uncertain alignment until the second base is added. This does not establish completion. Future placements are not mistakes.

## Why this is easier

The previous target had eight pieces in five layers, including front/back pairs. This target reduces height and removes hidden rear upper pieces. The vision prompt requires an unclear result when occlusion prevents checking an area. Unknown pieces suppress corrective instructions and prompt another view. The target, dialogue inventory and vision inventory all describe these same four pieces.

The dialogue still chooses its next instruction; the prompt requests checks between steps, but there is no deterministic step controller or persistent memory of verified blocks. Do not rely on memory to establish final success. All four pieces must be visible and match the target in the current check.

## Check what NAO actually sees first

From `experiment/experiment`, replace `ROBOT_IP` below with your robot's IP address:

```powershell
python tools/camera_probe.py ROBOT_IP --set-head --camera 0 --out tmp/camera_top
python tools/camera_probe.py ROBOT_IP --set-head --camera 1 --out tmp/camera_bottom
```

Open the JPEGs in those folders. Put a light-blue piece on the marked build spot, then test the full wall. The whole wall and the tops of the pieces should be in frame. Move the build spot farther from or closer to NAO as needed, clear hands away, and use even lighting. The tool checks photo capture and video fallback separately; a successful capture alone does not prove that blocks are in view.

If needed, try another downward angle, for example:

```powershell
python tools/camera_probe.py ROBOT_IP --set-head --camera 1 --pitch 0.45 --out tmp/camera_bottom_down
```

Save the successful `CAMERA_INDEX`, `HEAD_PITCH`, and `HEAD_YAW` values in `config.py`. The probe only previews these values; it does not save them. The default remains the top camera because the robot's physical setup has not been measured here. Use the saved probe image to confirm framing before running a participant session. Raw and model-input photos from session checks are also saved in the participant data folder for diagnosis.

Start with `REFERENCE_PHOTO_PATH = None`. After evaluating the baseline, optionally set `REFERENCE_PHOTO_PATH` in `config.py` to a photo of the finished wall taken with that same camera and pose. It supplies examples of the pieces and lighting; it is not treated as evidence of the current build.

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

Press a foot bumper to check the build. Vision still runs on demand, rather than continuously. Checks preserve more image detail, distinguish your two target footprints and the difference between light blue and blue, and ask for a clearer view if the frame is unclear or no blocks are seen. Uncertain extra blocks prevent a success result.

## Offline verification

From the repository root, with Pillow installed:

```powershell
python -m unittest discover -s experiment/experiment/tests -v
```

The regression suite covers the four-piece inventory, correct and incorrect wall observations, missing/hidden/uncertain pieces, blank frames, light-blue versus blue, photo paths, head positioning, gesture overlap/cooldown, and restoration of autonomous movement settings. These tests use simulated observations and robot services. They do not measure actual image-recognition accuracy or physical motion.

## Rehearse before the demo

Use the actual NAO camera and final lighting. Capture several completed walls and incomplete or incorrect walls (missing red, red on the wrong row, offset red). Place them under `test_photos/correct`, `test_photos/near_miss` or `test_photos/wrong` in `experiment/experiment`. Keep hand-obscured images for separately checking that NAO requests a clearer view.

From `experiment/experiment`:

```powershell
python tools/eval_vision.py test_photos --models gpt-4.1 --repeat 3 --no-reference
```

Review false matches, missed correct walls, and inconsistent repeats. Rehearse all four placements with a fresh participant ID. Clear hands and press the bumper at each step. The photo evaluator checks final match decisions; it does not test spoken guidance. Use the model already configured as a baseline before changing models. A reference photo must also be evaluated rather than assumed to help.

Offline tests use simulated observations. Live camera/API evaluation and physical robot rehearsal must be done on your setup. Never substitute a recorded image for a live check during the demo.
