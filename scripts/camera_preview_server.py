from __future__ import annotations

import argparse
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class CameraState:
    def __init__(self, camera_index: int) -> None:
        self.camera_index = camera_index
        self.lock = threading.Lock()
        self.frame: bytes | None = None
        self.running = True

    def start(self) -> None:
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()

    def _run(self) -> None:
        import cv2  # type: ignore[import-not-found]

        capture: Any | None = None
        picamera: Any | None = None
        try:
            try:
                from picamera2 import Picamera2  # type: ignore[import-not-found]

                picamera = Picamera2(self.camera_index)
                config = picamera.create_video_configuration(
                    main={"format": "RGB888", "size": (640, 480)}
                )
                picamera.configure(config)
                picamera.start()
                time.sleep(1.0)
            except Exception as exc:
                print(f"Picamera2 unavailable, trying OpenCV: {exc}", flush=True)
                capture = cv2.VideoCapture(self.camera_index)
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

            while self.running:
                if picamera is not None:
                    frame = picamera.capture_array()
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                else:
                    ok, frame = capture.read()
                    if not ok:
                        time.sleep(0.1)
                        continue

                ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if ok:
                    with self.lock:
                        self.frame = encoded.tobytes()
                time.sleep(0.03)
        finally:
            if picamera is not None:
                picamera.stop()
            if capture is not None:
                capture.release()


def make_handler(state: CameraState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path in {"/", "/index.html"}:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    b"""<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RAFEEQ Camera Preview</title>
  <style>
    body { margin: 0; background: #111; color: white; font-family: sans-serif; }
    header { padding: 12px 16px; background: #202020; }
    img { display: block; width: 100vw; height: calc(100vh - 48px); object-fit: contain; }
  </style>
</head>
<body>
  <header>RAFEEQ Camera Preview</header>
  <img src="/stream.mjpg">
</body>
</html>"""
                )
                return

            if self.path == "/snapshot.jpg":
                frame = self._latest_frame()
                if frame is None:
                    self.send_error(503, "No frame yet")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(frame)))
                self.end_headers()
                self.wfile.write(frame)
                return

            if self.path == "/stream.mjpg":
                self.send_response(200)
                self.send_header("Age", "0")
                self.send_header("Cache-Control", "no-cache, private")
                self.send_header("Pragma", "no-cache")
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.end_headers()
                while True:
                    frame = self._latest_frame()
                    if frame is None:
                        time.sleep(0.1)
                        continue
                    try:
                        self.wfile.write(b"--frame\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                        self.wfile.write(frame)
                        self.wfile.write(b"\r\n")
                        time.sleep(0.05)
                    except BrokenPipeError:
                        break
                return

            self.send_error(404)

        def _latest_frame(self) -> bytes | None:
            with state.lock:
                return state.frame

        def log_message(self, fmt: str, *args: object) -> None:
            print(f"{self.address_string()} - {fmt % args}", flush=True)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--camera-index", type=int, default=0)
    args = parser.parse_args()

    state = CameraState(args.camera_index)
    state.start()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(state))
    print(f"RAFEEQ camera preview: http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    finally:
        state.running = False
        server.server_close()


if __name__ == "__main__":
    main()
