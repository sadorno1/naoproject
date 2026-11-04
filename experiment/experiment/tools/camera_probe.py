#checks which camera capture method works on this NAO and saves a sample image from each
#usage: python tools/camera_probe.py <robot_ip> [--set-head] [--out DIR]
#  --set-head  moves the head to HEAD_YAW / HEAD_PITCH from config.py first, so you can check the
#              framing of the marked build spot (this is the pose used for the whole session)
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import config
from nao_proxy import NaoProxy, photo_result_path


def try_photo_capture(session, ssh_sftp, out_dir):
    photo = session.service("ALPhotoCapture")
    photo.setCameraID(config.CAMERA_INDEX)
    photo.setResolution(config.PHOTO_RESOLUTION)
    photo.setPictureFormat("jpg")
    t0 = time.perf_counter()
    result = photo.takePicture(config.ROBOT_PHOTO_DIR, "probe")
    t_capture = time.perf_counter() - t0
    #takePicture returns the saved path(s); fall back to the expected name if it returns nothing useful
    robot_path = photo_result_path(result, config.ROBOT_PHOTO_DIR, "probe")
    local_path = os.path.join(out_dir, "probe_photocapture.jpg")
    t1 = time.perf_counter()
    ssh_sftp.get(robot_path, local_path)
    t_transfer = time.perf_counter() - t1
    return local_path, t_capture, t_transfer, f"takePicture returned {result!r}"


def try_video_device(session, out_dir):
    from PIL import Image
    video = session.service("ALVideoDevice")
    t0 = time.perf_counter()
    handle = video.subscribeCamera("camera_probe", config.CAMERA_INDEX, config.VIDEO_RESOLUTION, 11, 5)  #11 = kRGBColorSpace
    try:
        time.sleep(config.VIDEO_WARMUP_S)
        frame = video.getImageRemote(handle)
    finally:
        video.unsubscribe(handle)
    t_capture = time.perf_counter() - t0
    if not frame:
        raise RuntimeError("getImageRemote returned no image")
    width, height, data = frame[0], frame[1], frame[6]
    image = Image.frombytes("RGB", (width, height), bytes(data))
    local_path = os.path.join(out_dir, "probe_videodevice.jpg")
    image.save(local_path, "JPEG", quality=95)
    return local_path, t_capture, 0.0, f"{width}x{height}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("robot_ip")
    parser.add_argument("--set-head", action="store_true")
    parser.add_argument("--camera", type=int, choices=[0, 1], default=config.CAMERA_INDEX,
                        help="0 = top camera, 1 = bottom camera; inspect both views before choosing")
    parser.add_argument("--pitch", type=float, default=config.HEAD_PITCH)
    parser.add_argument("--yaw", type=float, default=config.HEAD_YAW)
    parser.add_argument("--out", default=os.path.join(config.TMP_DIR, "camera_probe"))
    args = parser.parse_args()
    if not -0.5 <= args.pitch <= 0.5 or not -1.0 <= args.yaw <= 1.0:
        parser.error("use pitch between -0.5 and 0.5, yaw between -1.0 and 1.0 radians")
    config.CAMERA_INDEX = args.camera
    os.makedirs(args.out, exist_ok=True)

    import qi
    import paramiko
    session = qi.Session()
    session.connect(f"tcp://{args.robot_ip}:{config.ROBOT_PORT}")
    print(f"Connected to NAO at {args.robot_ip}")
    try:
        print(f"NAOqi version: {session.service('ALSystem').systemVersion()}")
    except Exception as e:
        print(f"Could not read NAOqi version: {e}")

    nao = NaoProxy(session)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    sftp = None
    results = {}
    try:
        if args.set_head:
            nao.quiet_movement()
            nao.set_head_pose(yaw=args.yaw, pitch=args.pitch)
            print(f"Head set to yaw={args.yaw} pitch={args.pitch}; camera={args.camera}")
        ssh.connect(args.robot_ip, username=config.ROBOT_USER, password=config.ROBOT_PASS)
        ssh.exec_command(f"mkdir -p {config.ROBOT_WORK_DIR}")[1].channel.recv_exit_status()
        sftp = ssh.open_sftp()
        for name, run in (("ALPhotoCapture", lambda: try_photo_capture(session, sftp, args.out)),
                          ("ALVideoDevice", lambda: try_video_device(session, args.out))):
            print(f"\n--- {name} ---")
            try:
                path, t_capture, t_transfer, detail = run()
                from PIL import Image
                with Image.open(path) as im:
                    size = im.size
                print(f"OK  {detail}")
                print(f"    image size {size}, capture {t_capture:.2f}s, transfer {t_transfer:.2f}s")
                print(f"    saved to {path}")
                results[name] = True
            except Exception as e:
                print(f"FAILED: {e}")
                results[name] = False
    finally:
        try:
            if sftp is not None:
                sftp.close()
        finally:
            ssh.close()
            nao.restore_movement()

    print("\nSummary:")
    print("Open the saved images: the entire wall, large studs, and block seams must be visible.")
    print(f"If framing works, set CAMERA_INDEX={args.camera}, HEAD_PITCH={args.pitch}, HEAD_YAW={args.yaw} in config.py.")
    for name, ok in results.items():
        print(f"  {name:<15} {'works' if ok else 'does not work'}")
    if results.get("ALPhotoCapture"):
        print("Set CAPTURE_METHOD = 'auto' or 'photo' in config.py (higher resolution).")
    elif results.get("ALVideoDevice"):
        print("Set CAPTURE_METHOD = 'video' in config.py.")
    else:
        print("Neither method worked; check the camera index and NAOqi services.")
    return 0 if any(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
