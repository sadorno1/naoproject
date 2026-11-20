"""Run separately from run_session.py. Tap the front head sensor to save each step photo."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import queue
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from build_workflow import ACTIVITIES, BUILDS_DIR, read_json
from nao_proxy import connect_robot, NaoProxy
from reference_capture import HeadCaptureTrigger, capture_robot, save_reference, is_control_step
from robot_link import RobotLink


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("robot_ip")
    parser.add_argument("--build", required=True, choices=ACTIVITIES)
    parser.add_argument("--builds-dir", type=Path, default=BUILDS_DIR)
    parser.add_argument("--start-step", type=int, default=None, help="default: next step without a saved photo")
    args = parser.parse_args(argv)
    folder = args.builds_dir / args.build
    if not (folder / "build.json").is_file():
        parser.error(f"Missing {folder / 'build.json'}")
    if read_json(folder / "build.json").get("mode") == "controls":
        parser.error("The controls tutorial needs no photos. Choose build_1, build_2 or build_3.")
    number = args.start_step if args.start_step is not None else 1
    if number < 1:
        parser.error("--start-step must be positive")
    if args.start_step is None:
        while (is_control_step(args.builds_dir, args.build, number)
               or (folder / f"step_{number:02d}" / "reference.jpg").exists()):
            number += 1
    if is_control_step(args.builds_dir, args.build, number):
        parser.error("That step practices a control, not a build. Use --start-step 3 for the tutorial mini-build.")
    if (folder / f"step_{number:02d}" / "reference.jpg").exists():
        parser.error("That step already has a photo. Move the old photo aside explicitly before retaking it.")
    session = connect_robot(args.robot_ip)
    if session is None:
        return 1
    nao = NaoProxy(session)
    link = None
    trigger = HeadCaptureTrigger()
    scratch = folder / ".capture_pending.jpg"
    try:
        link = RobotLink(args.robot_ip)
        nao.quiet_movement()
        nao.prepare_posture()
        nao.set_head_pose(wait=True)
        if not nao.subscribe("FrontTactilTouched", trigger.touch):
            raise RuntimeError("Could not subscribe to the front head sensor")
        print("REFERENCE CAPTURE MODE — stop run_session.py before using this tool.")
        print("Build the cumulative state for each step. Tap and release the FRONT HEAD sensor to save.")
        print("Captures happen after release and settling. Bumpers are inactive here. Ctrl+C stops.")
        print(f"Next photo: {args.build}/step_{number:02d}/reference.jpg")
        while True:
            try:
                trigger.requests.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                time.sleep(0.8)
                nao.set_head_pose(wait=True)
                method = capture_robot(nao, link, scratch)
                metadata = dict(captured_at=datetime.now(timezone.utc).isoformat(), camera_index=config.CAMERA_INDEX,
                                head_pitch=config.HEAD_PITCH, head_yaw=config.HEAD_YAW,
                                posture=config.POSTURE, capture_method=method)
                photo = save_reference(args.builds_dir, args.build, number, scratch.read_bytes(), metadata)
                print(f"Saved {photo}. Review it; fill instruction/expected and set ready=true in step.json.")
                number += 1
                while (is_control_step(args.builds_dir, args.build, number)
                       or (folder / f"step_{number:02d}" / "reference.jpg").exists()):
                    number += 1
                print(f"Next photo: {args.build}/step_{number:02d}/reference.jpg")
            except Exception as e:
                print(f"Photo not saved for step {number}: {e}. Fix the problem and tap again.")
            finally:
                scratch.unlink(missing_ok=True)
                trigger.finish()
    except KeyboardInterrupt:
        print("\nReference capture stopped. No existing photos were overwritten.")
    finally:
        scratch.unlink(missing_ok=True)
        nao.restore_movement()
        if link:
            link.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
