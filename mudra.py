#!/usr/bin/env python3
"""mudra — control your mouse with hand gestures via a webcam.

A webcam "air-mouse" for Linux/Wayland. MediaPipe hand models (21 keypoints)
run through OpenCV's dnn module track your hand; the cursor and clicks are
injected through an evdev/uinput virtual mouse, so it works natively on
Wayland (where X11 tools like xdotool/pyautogui can't move the real cursor).

Gestures:
  move        : point with your index finger (the fingertip is the cursor)
  left click  : pinch thumb + middle together (hold to drag)
  right click : pinch thumb + index together
  grab & move : make a fist -> holds the left button; move your fist to drag and
                open your hand to drop (great for moving windows/objects)

Hotkeys (read globally via evdev, so they work regardless of window focus):
  q / Esc quit · p pause   (Ctrl+C also quits)

No pip, no venv, no PyTorch: the models are small ONNX files executed by the
distro's python3-opencv. See mp_hand.py.
"""
from __future__ import annotations

import argparse
import math
import os
import pathlib
import select
import signal
import sys
import threading
import time
from collections import deque

import numpy as np

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPainter, QColor, QFont
from PyQt6.QtWidgets import QApplication, QWidget

HERE = pathlib.Path(__file__).resolve().parent
PALM_MODEL = HERE / "palm_detection_mediapipe_2023feb.onnx"
HAND_MODEL = HERE / "handpose_estimation_mediapipe_2023feb.onnx"

# 21-keypoint hand layout (MediaPipe convention)
WRIST, THUMB_TIP, INDEX_MCP, INDEX_TIP = 0, 4, 5, 8
MIDDLE_MCP, MIDDLE_TIP, PINKY_MCP = 9, 12, 17
FINGER_TIPS = (8, 12, 16, 20)   # index, middle, ring, pinky
FINGER_PIPS = (6, 10, 14, 18)
PALM_MCPS = (5, 9, 13, 17)


# ---------------------------------------------------------------------------
# One-Euro filter: adaptive low-pass that trades lag for jitter sensibly.
# ---------------------------------------------------------------------------
class OneEuro:
    def __init__(self, freq=30.0, mincutoff=1.0, beta=0.02, dcutoff=1.0):
        self.freq, self.mincutoff, self.beta, self.dcutoff = (
            freq, mincutoff, beta, dcutoff)
        self._x_prev = None
        self._dx_prev = 0.0
        self._t_prev = None

    @staticmethod
    def _alpha(cutoff, freq):
        tau = 1.0 / (2 * math.pi * cutoff)
        te = 1.0 / freq
        return 1.0 / (1.0 + tau / te)

    def __call__(self, x, t=None):
        if t is None:
            t = time.monotonic()
        if self._x_prev is None:
            self._x_prev, self._t_prev = x, t
            return x
        dt = t - self._t_prev
        if dt > 0:
            self.freq = 1.0 / dt
        self._t_prev = t
        dx = (x - self._x_prev) * self.freq
        a_d = self._alpha(self.dcutoff, self.freq)
        dx_hat = a_d * dx + (1 - a_d) * self._dx_prev
        cutoff = self.mincutoff + self.beta * abs(dx_hat)
        a = self._alpha(cutoff, self.freq)
        x_hat = a * x + (1 - a) * self._x_prev
        self._x_prev, self._dx_prev = x_hat, dx_hat
        return x_hat


# ---------------------------------------------------------------------------
# Virtual mouse via evdev/uinput: a tablet-style *absolute* pointer (ABS_X/
# ABS_Y over a normalized 0..65535 range, like QEMU's usb-tablet). The
# compositor maps that range to the whole desktop, so no screen-size
# detection, no homing, no drift.
# ---------------------------------------------------------------------------
class VirtualMouse:
    RANGE = 65535

    def __init__(self):
        from evdev import AbsInfo, UInput, ecodes as e
        self.e = e
        cap = {
            e.EV_ABS: [
                (e.ABS_X, AbsInfo(value=self.RANGE // 2, min=0,
                                  max=self.RANGE, fuzz=0, flat=0,
                                  resolution=0)),
                (e.ABS_Y, AbsInfo(value=self.RANGE // 2, min=0,
                                  max=self.RANGE, fuzz=0, flat=0,
                                  resolution=0)),
            ],
            e.EV_REL: [e.REL_WHEEL],
            e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE],
        }
        try:
            self.ui = UInput(cap, name="mudra-pointer")
        except (PermissionError, OSError) as exc:
            raise SystemExit(
                f"Cannot open /dev/uinput ({exc}).\n"
                "Run ./setup.sh first (adds a udev rule + puts you in the "
                "'input' group), then launch via ./run.sh.")
        self.pos = np.array([0.5, 0.5])

    def move_to(self, target_norm):
        target = np.clip(target_norm, 0.0, 1.0)
        self.ui.write(self.e.EV_ABS, self.e.ABS_X,
                      int(round(target[0] * self.RANGE)))
        self.ui.write(self.e.EV_ABS, self.e.ABS_Y,
                      int(round(target[1] * self.RANGE)))
        self.ui.syn()
        self.pos = target

    def _btn(self, button):
        return {"left": self.e.BTN_LEFT, "right": self.e.BTN_RIGHT,
                "middle": self.e.BTN_MIDDLE}[button]

    def press(self, button="left"):
        self.ui.write(self.e.EV_KEY, self._btn(button), 1)
        self.ui.syn()

    def release(self, button="left"):
        self.ui.write(self.e.EV_KEY, self._btn(button), 0)
        self.ui.syn()

    def click(self, button="left"):
        self.press(button)
        time.sleep(0.03)
        self.release(button)

    def close(self):
        try:
            self.ui.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Global hotkeys via evdev: works no matter which window has focus (important
# while the cursor is being driven by your hand). Observes only, never grabs.
# ---------------------------------------------------------------------------
class KeyListener:
    def __init__(self):
        self.devs, self.ec, self.kmap = [], None, {}
        try:
            from evdev import InputDevice, list_devices, ecodes
        except Exception:
            return
        self.ec = ecodes
        for path in list_devices():
            try:
                d = InputDevice(path)
                caps = d.capabilities().get(ecodes.EV_KEY, [])
                if ecodes.KEY_Q in caps and ecodes.KEY_ENTER in caps:
                    os.set_blocking(d.fd, False)
                    self.devs.append(d)
                else:
                    d.close()
            except Exception:
                pass
        self.kmap = {ecodes.KEY_Q: "q", ecodes.KEY_ESC: "q", ecodes.KEY_P: "p"}

    def poll(self):
        out = []
        if not self.devs:
            return out
        r, _, _ = select.select(self.devs, [], [], 0)
        for d in r:
            try:
                for ev in d.read():
                    if ev.type == self.ec.EV_KEY and ev.value == 1:
                        c = self.kmap.get(ev.code)
                        if c:
                            out.append(c)
            except OSError:
                pass
        return out

    def close(self):
        for d in self.devs:
            try:
                d.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Hand geometry helpers
# ---------------------------------------------------------------------------
def _dist(a, b):
    return float(np.hypot(a[0] - b[0], a[1] - b[1]))


def _palm_center(kp):
    return kp[list(PALM_MCPS)].mean(axis=0)


def _curled_count(kp):
    """How many of the 4 fingers are folded (tip nearer the wrist than its PIP).
    4 = fist, 0 = open hand. Robust to hand rotation."""
    w = kp[WRIST]
    return sum(1 for tip, pip in zip(FINGER_TIPS, FINGER_PIPS)
               if _dist(kp[tip], w) < _dist(kp[pip], w))


# ---------------------------------------------------------------------------
# Threaded camera: a grabber thread always keeps only the *newest* frame, so
# the processing loop never blocks on the camera and never works on a stale
# queued frame (V4L2/GStreamer buffer one or more frames otherwise — that's
# pure cursor latency).
# ---------------------------------------------------------------------------
class Camera:
    def __init__(self, index):
        import cv2
        self.cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
        if not self.cap.isOpened():            # fall back to any backend
            self.cap = cv2.VideoCapture(index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.ok = self.cap.isOpened()
        self._lock = threading.Lock()
        self._frame = None
        self._seq = 0
        self._taken = 0
        self._run = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        if self.ok:
            self._thread.start()

    def _loop(self):
        while self._run:
            ok, f = self.cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            with self._lock:
                self._frame, self._seq = f, self._seq + 1

    def latest(self):
        """The newest frame, or None if it was already handed out."""
        with self._lock:
            if self._frame is None or self._seq == self._taken:
                return None
            self._taken = self._seq
            return self._frame

    def release(self):
        self._run = False
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self.cap.release()


# ---------------------------------------------------------------------------
# Hand tracking: MediaPipe palm-detection + hand-landmark ONNX models via
# OpenCV dnn (see mp_hand.py). Like the real MediaPipe pipeline, the palm
# detector only runs to (re)acquire the hand; while tracking, each frame's
# crop is derived from the previous frame's landmarks (~2x faster).
# ---------------------------------------------------------------------------
class HandTracker:
    def __init__(self, palm_model, hand_model, conf):
        from mp_hand import MPPalmDet, MPHandPose, palm_from_landmarks
        self._palm_from_landmarks = palm_from_landmarks
        self.detector = MPPalmDet(str(palm_model))
        self.landmarker = MPHandPose(str(hand_model), conf_threshold=conf)
        self._palm = None

    def __call__(self, frame):
        """Return (kp, conf) — 21 (x, y) landmarks + confidence — or None."""
        if self._palm is not None:
            r = self.landmarker.infer(frame, self._palm)
            if r is not None:
                self._palm = self._palm_from_landmarks(r[0])
                return r
            self._palm = None
        palms = self.detector.infer(frame)
        if len(palms) == 0:
            return None
        i = int(np.argmax((palms[:, 2] - palms[:, 0])
                          * (palms[:, 3] - palms[:, 1])))   # largest palm
        r = self.landmarker.infer(frame, palms[i])
        if r is not None:
            self._palm = self._palm_from_landmarks(r[0])
        return r


# ---------------------------------------------------------------------------
# The app: a small preview window driven by a QTimer.
# ---------------------------------------------------------------------------
class HandMouse(QWidget):
    def __init__(self, model, cap, mouse, keys, args):
        super().__init__()
        self.model, self.cap, self.mouse, self.keys = model, cap, mouse, keys
        self.args = args
        self.fx = OneEuro(mincutoff=args.mincutoff, beta=args.beta)
        self.fy = OneEuro(mincutoff=args.mincutoff, beta=args.beta)
        self._hist = deque(maxlen=max(1, args.median))  # cursor outlier rejection
        self._di = deque(maxlen=3)   # smoothed pinch distances
        self._dm = deque(maxlen=3)
        self.left_down = False
        self.right_until = 0.0
        self.grabbing = False
        self._grab_c0 = None
        self._grab_a0 = None
        self._fist_on = False
        self._fist_flip = 0
        self._miss = 0
        self.paused = False
        self.status = "show your hand"
        self.fps = 0.0
        self._last = time.monotonic()
        self._qbuf = None
        self._kp_mirror = None
        self.setWindowTitle("mudra")
        self.resize(560, 420)
        self.show()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(2)

    def _release_left(self):
        if self.left_down:
            self.mouse.release("left")
            self.left_down = False
        self.grabbing = False

    def tick(self):
        for k in self.keys.poll():
            if k == "q":
                self.quit()
                return
            if k == "p":
                self.paused = not self.paused
                if self.paused:
                    self._release_left()
        frame = self.cap.latest()
        if frame is None:
            return
        now = time.monotonic()
        dt = now - self._last
        self._last = now
        if dt > 0:
            self.fps = 0.9 * self.fps + 0.1 / dt

        r = self.model(frame)
        kp = None
        if r is not None:
            self._miss = 0
            kp, hand_conf = r
            conf = np.full(len(kp), hand_conf)
            self._handle_hand(kp, conf, frame.shape, now)
        else:
            self._miss += 1
            if self._miss >= 5:            # tolerate brief detection dropouts
                self.status = "no hand"
                self._release_left()
        self._draw(frame, kp)

    def _handle_hand(self, kp, conf, shape, now):
        h, w = shape[:2]
        m = self.args.margin
        span = max(1e-3, 1.0 - 2 * m)

        # Pinch distances, normalised by a rotation-stable hand scale (the larger
        # of palm width and palm length) and median-smoothed across frames so
        # they don't flicker across the threshold.
        scale = max(_dist(kp[INDEX_MCP], kp[PINKY_MCP]),
                    _dist(kp[WRIST], kp[MIDDLE_MCP])) + 1e-3
        self._di.append(_dist(kp[THUMB_TIP], kp[INDEX_TIP]) / scale)
        self._dm.append(_dist(kp[THUMB_TIP], kp[MIDDLE_TIP]) / scale)
        d_index = float(np.median(self._di))
        d_middle = float(np.median(self._dm))
        on, off = self.args.pinch, self.args.pinch + 0.18  # hysteresis

        # Fist detection (>=3 fingers curled), debounced over 2 frames.
        fist_now = self.args.grab and _curled_count(kp) >= 3
        if fist_now == self._fist_on:
            self._fist_flip = 0
        else:
            self._fist_flip += 1
            if self._fist_flip >= 2:
                self._fist_on = fist_now
                self._fist_flip = 0
        fist = self._fist_on

        # Enter/leave grab. On grab start, remember where the cursor and palm
        # were so we can drag *relatively* (no jump to the hand position).
        if fist and not self.grabbing:
            self.grabbing = True
            self._grab_c0 = self.mouse.pos.copy()
            c = _palm_center(kp)
            self._grab_a0 = np.array([1.0 - c[0] / w, c[1] / h])
            self._hist.clear()
        elif not fist and self.grabbing:
            self.grabbing = False

        # --- cursor ---
        if self.grabbing:
            c = _palm_center(kp)
            a = np.array([1.0 - c[0] / w, c[1] / h])
            tgt = self._grab_c0 + (a - self._grab_a0) / span   # relative drag
            pos = np.array([self.fx(float(np.clip(tgt[0], 0, 1)), now),
                            self.fy(float(np.clip(tgt[1], 0, 1)), now)])
            if not self.paused:
                self.mouse.move_to(pos)
            pointing = True
        else:
            # follow index tip; skip while it's pinching (right-click) or unseen
            pointing = conf[INDEX_TIP] >= 0.2 and d_index > off
            if pointing:
                nx = 1.0 - kp[INDEX_TIP][0] / w
                ny = kp[INDEX_TIP][1] / h
                self._hist.append((nx, ny))
                mx = float(np.median([p[0] for p in self._hist]))
                my = float(np.median([p[1] for p in self._hist]))
                tx = float(np.clip((mx - m) / span, 0, 1))
                ty = float(np.clip((my - m) / span, 0, 1))
                pos = np.array([self.fx(tx, now), self.fy(ty, now)])
                if not self.paused:
                    self.mouse.move_to(pos)

        # --- buttons: left = fist-grab OR thumb+middle pinch; right = thumb+index
        want_left = self.grabbing or (
            not fist and d_middle < (off if self.left_down else on))
        if not self.paused:
            if want_left and not self.left_down:
                self.mouse.press("left")
                self.left_down = True
            elif not want_left and self.left_down:
                self.mouse.release("left")
                self.left_down = False
            if (not fist) and (not self.left_down) and (d_index < on) \
                    and now > self.right_until:
                self.mouse.click("right")
                self.right_until = now + 0.6

        if self.grabbing:
            self.status = "GRAB / move (fist)"
        elif self.left_down:
            self.status = "DRAG / L-click"
        else:
            self.status = (("track" if pointing else "index hidden") +
                           f"  L(mid)={d_middle:.2f} R(idx)={d_index:.2f}")

    def _draw(self, frame, kp):
        import cv2
        disp = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
        self._qbuf = np.ascontiguousarray(disp)
        h, w, _ = self._qbuf.shape
        self._qimg = QImage(self._qbuf.data, w, h, 3 * w,
                            QImage.Format.Format_RGB888)
        self._kp_mirror = None
        if kp is not None:
            mk = kp.copy()
            mk[:, 0] = w - mk[:, 0]  # mirror to match flipped preview
            self._kp_mirror = (mk, w, h)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        if self._qbuf is not None:
            p.drawImage(self.rect(), self._qimg)
            if self._kp_mirror is not None:
                mk, fw, fh = self._kp_mirror
                sx, sy = self.width() / fw, self.height() / fh

                def pt(i):
                    return int(mk[i][0] * sx), int(mk[i][1] * sy)
                col = QColor(70, 220, 70) if self.left_down else QColor(255, 200, 0)
                p.setPen(col)
                for i in (THUMB_TIP, INDEX_TIP, MIDDLE_TIP):
                    x, y = pt(i)
                    p.drawEllipse(x - 6, y - 6, 12, 12)
                p.drawLine(*pt(THUMB_TIP), *pt(INDEX_TIP))
        p.setPen(QColor(255, 255, 0))
        p.setFont(QFont("sans", 11))
        tag = "PAUSED" if self.paused else self.status
        p.drawText(8, 22, f"mudra | {self.fps:4.1f} fps | {tag}")
        p.setPen(QColor(160, 160, 160))
        p.drawText(8, self.height() - 10,
                   "fist=grab/move · thumb+middle=L-click · thumb+index=R-click "
                   "· q quit · p pause")

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Q, Qt.Key.Key_Escape):
            self.quit()

    def quit(self):
        self.timer.stop()
        self._release_left()
        self.cap.release()
        self.mouse.close()
        self.keys.close()
        QApplication.instance().quit()


def build_args():
    p = argparse.ArgumentParser(description="mudra — hand-gesture air-mouse.")
    p.add_argument("--camera", type=int, default=0)
    p.add_argument("--conf", type=float, default=0.8,
                   help="hand confidence threshold (lower = keeps tracking "
                        "harder poses, more false positives)")
    p.add_argument("--margin", type=float, default=0.15,
                   help="frame edge fraction mapped outside the screen")
    p.add_argument("--pinch", type=float, default=0.62,
                   help="pinch close threshold (dist/hand-scale); higher = easier")
    p.add_argument("--no-grab", dest="grab", action="store_false", default=True,
                   help="disable fist-to-grab dragging")
    p.add_argument("--median", type=int, default=3,
                   help="frames of median filtering (rejects keypoint jumps; "
                        "more = steadier but laggier)")
    p.add_argument("--mincutoff", type=float, default=1.0,
                   help="One-Euro: lower = smoother/steadier when holding still")
    p.add_argument("--beta", type=float, default=0.05,
                   help="One-Euro: higher = snappier on fast moves")
    return p.parse_args()


def main():
    args = build_args()
    for m in (PALM_MODEL, HAND_MODEL):
        if not m.exists():
            sys.exit(f"Missing hand model: {m}\nRun ./setup.sh to fetch it.")

    print("inference=OpenCV-dnn (CPU)  pointer=absolute (uinput tablet)")
    model = HandTracker(PALM_MODEL, HAND_MODEL, args.conf)

    cap = Camera(args.camera)
    if not cap.ok:
        sys.exit(f"Cannot open camera {args.camera}.")
    warm, deadline = 0, time.monotonic() + 5.0
    while warm < 3 and time.monotonic() < deadline:
        f = cap.latest()
        if f is None:
            time.sleep(0.005)
            continue
        model(f)                 # warm up the inference graph
        warm += 1

    app = QApplication(sys.argv)
    keys = KeyListener()
    if not keys.devs:
        print("WARNING: no readable keyboard via evdev; use Ctrl+C to quit.")
    mouse = VirtualMouse()
    win = HandMouse(model, cap, mouse, keys, args)  # noqa: F841
    signal.signal(signal.SIGINT, lambda *_: win.quit())
    print("mudra running. Point with your index finger; pinch to click; "
          "fist to grab.")
    rc = app.exec()
    print("\nbye.")
    sys.exit(rc)


if __name__ == "__main__":
    main()
