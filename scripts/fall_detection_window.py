from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from typing import Any

import cv2  # type: ignore[import-not-found]

from rafeeq_robot.detection.webcam_demo import FrameMotionFallDetector


class PiCamera:
    def __init__(self, camera_index: int) -> None:
        from picamera2 import Picamera2  # type: ignore[import-not-found]

        self.camera = Picamera2(camera_index)
        config = self.camera.create_video_configuration(
            main={"format": "RGB888", "size": (640, 480)}
        )
        self.camera.configure(config)
        self.camera.start()
        time.sleep(1.0)

    def read(self) -> tuple[bool, Any]:
        frame = self.camera.capture_array()
        return True, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

    def release(self) -> None:
        self.camera.stop()


def draw_status(frame: Any, detector: FrameMotionFallDetector, triggered: bool, cooldown: float) -> None:
    height, width = frame.shape[:2]
    overlay = frame.copy()
    alert = triggered or cooldown > time.monotonic()
    color = (0, 0, 220) if alert else (24, 120, 24)
    cv2.rectangle(overlay, (0, 0), (width, 118), color, -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

    status = "POSSIBLE FALL DETECTED" if alert else "MONITORING - FALL DETECTION ACTIVE"
    cv2.putText(frame, status, (18, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.82, (255, 255, 255), 2)

    metrics = detector.last_metrics
    if metrics is None:
        detail = "Move in view. Stand upright first, then safely lower sideways for test."
    else:
        detail = (
            f"aspect={metrics.body_aspect_ratio:.2f} "
            f"low_y={metrics.hip_y:.2f} "
            f"descent={metrics.descent:.2f} "
            f"armed={metrics.recently_upright} "
            f"candidate={metrics.candidate_frames}"
        )
    cv2.putText(frame, detail, (18, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 2)
    cv2.putText(
        frame,
        "Q or ESC closes this window. Start rafeeq-camera service after testing.",
        (18, 102),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 255, 255),
        1,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--confirmation-frames", type=int, default=3)
    args = parser.parse_args()

    camera = PiCamera(args.camera_index)
    detector = FrameMotionFallDetector(
        confirmation_frames=max(1, args.confirmation_frames),
        min_area_ratio=0.02,
    )
    window_name = "RAFEEQ Fall Detection Camera"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 960, 720)
    cooldown_until = 0.0

    print("RAFEEQ desktop fall-detection window started.", flush=True)
    print("Press Q or ESC in the camera window to close.", flush=True)

    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                print("Camera did not return a frame.", flush=True)
                time.sleep(0.1)
                continue
            result = detector.analyze(frame, datetime.now(timezone.utc))
            if result.is_possible_fall:
                cooldown_until = time.monotonic() + 4.0
                print(
                    f"POSSIBLE FALL confidence={result.confidence:.2f} reasons={result.reason_codes}",
                    flush=True,
                )
            draw_status(frame, detector, result.is_possible_fall, cooldown_until)
            cv2.imshow(window_name, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
    finally:
        camera.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
