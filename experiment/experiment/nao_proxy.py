#Qi / NAO wrapper for the experiment, extended from the NaoProxy in lab 3.
#every method falls back to a printed mock when its service is unavailable (robot not connected / dry run)
import time
import posixpath

import config


def photo_result_path(result, folder, name):
    """NAOqi may return [directory, filename] or a complete filename."""
    if isinstance(result, (list, tuple)) and result:
        if len(result) >= 2 and isinstance(result[0], str) and isinstance(result[1], str):
            return posixpath.join(result[0], result[1])
        if isinstance(result[0], str):
            return result[0]
    if isinstance(result, str):
        return result
    return posixpath.join(folder, name + ".jpg")


#connects to the robot; returns None on failure so callers can fall back to mocks like lab 3 did
def connect_robot(robot_ip, port=config.ROBOT_PORT):
    try:
        import qi
    except ImportError:
        print("The qi module is not installed; running without the robot.")
        return None
    session = qi.Session()
    try:
        session.connect(f"tcp://{robot_ip}:{port}")
        print(f"Connected to NAO at {robot_ip}")
        return session
    except RuntimeError as e:
        print(f"Failed to connect to NAO at {robot_ip}: {e}")
        return None


def _load_service(session, name):
    if session is None:
        return None
    try:
        return session.service(name)
    except Exception as e:
        print(f"Failed to load {name}: {e}")
        return None


class NaoProxy:
    def __init__(self, session):
        self.session = session
        self.leds = _load_service(session, "ALLeds")
        self.posture = _load_service(session, "ALRobotPosture")
        self.motion = _load_service(session, "ALMotion")
        self.animate = _load_service(session, "ALBehaviorManager")
        self.video = _load_service(session, "ALVideoDevice")
        self.photo = _load_service(session, "ALPhotoCapture")
        self.audio_recorder = _load_service(session, "ALAudioRecorder")
        self.audio_player = _load_service(session, "ALAudioPlayer")
        self.audio_device = _load_service(session, "ALAudioDevice")
        self.memory = _load_service(session, "ALMemory")
        self.system = _load_service(session, "ALSystem")
        self.awareness = _load_service(session, "ALBasicAwareness")
        self.autonomous_moves = _load_service(session, "ALAutonomousMoves")
        self._movement_restore = []

        # Reset any stuck recording states from previous crashed runs
        if self.audio_recorder:
            try:
                self.audio_recorder.stopMicrophonesRecording()
            except Exception:
                pass

        self._subscribers = []        #keep qi subscribers alive
        self._installed_cache = {}
        self._started_behaviors = []
        self._last_gesture_at = None

    def quiet_movement(self):
        """Temporarily pause competing head/body movement on NAOqi 2.1."""
        if not config.QUIET_AUTONOMOUS_MOVEMENT or self._movement_restore:
            return
        controls = [
            (self.awareness, "isAwarenessRunning", "stopAwareness", "startAwareness"),
            (self.autonomous_moves, "getBackgroundStrategy", "setBackgroundStrategy", "none"),
            (self.autonomous_moves, "getExpressiveListeningEnabled", "setExpressiveListeningEnabled", False),
        ]
        for service, getter, setter, value in controls:
            if service is None:
                continue
            try:
                previous = getattr(service, getter)()
                if getter == "isAwarenessRunning":
                    if previous:
                        getattr(service, setter)()
                        self._movement_restore.append((service, value, ()))
                else:
                    getattr(service, setter)(value)
                    self._movement_restore.append((service, setter, (previous,)))
            except Exception as e:
                print(f"Could not pause {getter}: {e}")

    def restore_movement(self):
        for service, setter, args in reversed(self._movement_restore):
            try:
                getattr(service, setter)(*args)
            except Exception as e:
                print(f"Could not restore {setter}: {e}")
        self._movement_restore.clear()

    @property
    def connected(self):
        return self.session is not None

    def naoqi_version(self):
        if self.system:
            try:
                return self.system.systemVersion()
            except Exception:
                return None
        return None

    #wakes the motors and goes to the configured posture ("Sit" or "Stand")
    def prepare_posture(self, posture=config.POSTURE):
        if self.motion and self.posture:
            print(f"Going to posture {posture}...")
            self.motion.wakeUp()
            self.posture.goToPosture(posture, config.POSTURE_SPEED)
        else:
            print(f"[Mock Motion]: Posture {posture}")

    #sets the fixed head pose used for the whole session (and for every photo)
    def set_head_pose(self, yaw=config.HEAD_YAW, pitch=config.HEAD_PITCH, wait=True):
        if self.motion:
            self.motion.setStiffnesses("Head", 1.0)
            if wait:
                self.motion.angleInterpolationWithSpeed(["HeadYaw", "HeadPitch"], [yaw, pitch], config.HEAD_SPEED)
                time.sleep(config.HEAD_SETTLE_S)
            else:
                self.motion.setAngles(["HeadYaw", "HeadPitch"], [yaw, pitch], config.HEAD_SPEED)
        else:
            print(f"[Mock Motion]: Head yaw={yaw} pitch={pitch}")

    #sets the speaker volume once at startup
    def set_volume(self, volume=config.VOLUME):
        if self.audio_device:
            self.audio_device.setOutputVolume(volume)
        else:
            print(f"[Mock AudioDevice]: Volume {volume}")

    def set_eyes(self, rgb):
        if self.leds:
            self.leds.fadeRGB("FaceLeds", rgb[0], rgb[1], rgb[2], 0.1)
        else:
            print(f"[Mock LEDs]: Eyes {rgb}")

    def _behavior_installed(self, path):
        if path not in self._installed_cache:
            try:
                self._installed_cache[path] = bool(self.animate.isBehaviorInstalled(path))
            except Exception:
                self._installed_cache[path] = False
        return self._installed_cache[path]

    #starts the animation for an expression name (non-blocking). returns (behavior_path, status)
    #seated, only Sit animations are used; a missing animation means no gesture rather than an unsafe one
    def change_expression(self, expression_name, posture=config.POSTURE, preview=False):
        table = config.SIT_ANIMATIONS if posture == "Sit" else config.STAND_ANIMATIONS
        path = table.get(expression_name)
        if path is None:
            return None, "unknown_expression"
        if not config.GESTURES_ENABLED and not preview:
            return path, "disabled"
        if not preview and self._last_gesture_at is not None and time.monotonic() - self._last_gesture_at < config.GESTURE_COOLDOWN_S:
            return path, "cooldown"
        if not self.animate:
            print(f"[Mock Expression change]: {expression_name}")
            return path, "mock"
        if not self._behavior_installed(path):
            print(f"Animation not installed, skipping gesture: {path}")
            return path, "not_installed"
        try:
            running = set(self.animate.getRunningBehaviors())
            if running.intersection(self._started_behaviors):
                return path, "busy"
            self.animate.startBehavior(path)
            self._started_behaviors = [path]
            self._last_gesture_at = time.monotonic()
            return path, "started"
        except Exception as e:
            print(f"Failed to start {path}: {e}")
            return path, f"error: {e}"

    #waits until the gestures we started have finished (used before taking a photo)
    def wait_for_gestures(self, timeout=config.GESTURE_WAIT_TIMEOUT_S):
        if not self.animate:
            return True
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            try:
                running = set(self.animate.getRunningBehaviors())
            except Exception:
                return False
            if not running.intersection(self._started_behaviors):
                self._started_behaviors = []
                return True
            time.sleep(0.1)
        return False

    def stop_gestures(self):
        """Stop only behaviors this session started; preserve tracking until they finish."""
        if self.animate:
            for path in self._started_behaviors:
                try:
                    self.animate.stopBehavior(path)
                except Exception as e:
                    print(f"Could not stop {path}: {e}")

    #starts recording audio from the robot's front microphone, as in lab 3
    def start_recording(self, path):
        if self.audio_recorder:
            self.audio_recorder.startMicrophonesRecording(path, "wav", 16000, [0, 0, 1, 0])
        else:
            print("[Mock AudioRecorder]: Start recording")

    def stop_recording(self):
        if self.audio_recorder:
            self.audio_recorder.stopMicrophonesRecording()
        else:
            print("[Mock AudioRecorder]: Stop recording")

    #plays a file already on the robot; blocks until playback finishes (volume is NOT changed here)
    def play_file(self, path):
        if self.audio_player:
            self.audio_player.playFile(path, 1.0, 0.0)
        else:
            print(f"[Mock AudioPlayer]: Playing {path}")

    #stops any playback in progress (used for barge-in)
    def stop_audio(self):
        if self.audio_player:
            try:
                self.audio_player.stopAll()
            except Exception as e:
                print(f"stopAll failed: {e}")

    #subscribes a callback(value) to an ALMemory event; returns False when not possible
    def subscribe(self, key, callback):
        if not self.memory:
            return False
        sub = self.memory.subscriber(key)
        sub.signal.connect(callback)
        self._subscribers.append(sub)
        return True

    #takes a jpeg with ALPhotoCapture on the robot; returns the robot-side path
    def capture_photo(self, folder=config.ROBOT_PHOTO_DIR, name=config.ROBOT_PHOTO_NAME):
        if not self.photo:
            raise RuntimeError("ALPhotoCapture not available")
        self.photo.setCameraID(config.CAMERA_INDEX)
        self.photo.setResolution(config.PHOTO_RESOLUTION)
        self.photo.setPictureFormat("jpg")
        result = self.photo.takePicture(folder, name)
        return photo_result_path(result, folder, name)

    #grabs one RGB frame with ALVideoDevice; returns a PIL image
    def capture_video_frame(self):
        if not self.video:
            raise RuntimeError("ALVideoDevice not available")
        from PIL import Image
        handle = self.video.subscribeCamera("experiment_check", config.CAMERA_INDEX,
                                            config.VIDEO_RESOLUTION, 11, 5)  #11 = kRGBColorSpace
        try:
            time.sleep(config.VIDEO_WARMUP_S)
            frame = self.video.getImageRemote(handle)
        finally:
            self.video.unsubscribe(handle)
        if not frame:
            raise RuntimeError("getImageRemote returned no image")
        return Image.frombytes("RGB", (frame[0], frame[1]), bytes(frame[6]))
