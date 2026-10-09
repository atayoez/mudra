#!/usr/bin/env python3
"""mudra — control your mouse with hand gestures via a webcam.

A webcam hand-mouse for Linux/Wayland. The default "desk" mode is designed
for a camera mounted vertically above the hand. The middle fingertip controls
the cursor while the other fingers act like dedicated mouse controls. The
original front-facing air-mouse remains available with --mode air.

Desk-mode controls:
  middle finger : cursor anchor
  index finger  : tap for left click
  ring finger   : tap for right click
  thumb         : lift/hold to drag; return to the desk to drop
  little finger : reserved for context-aware copy/paste
  4 fingers     : index+middle+ring+pinky on desk, move together = scroll

Air-mode gestures:
  move          : point with your index finger
  left click    : pinch thumb + middle together (hold to drag)
  right click   : pinch thumb + index together
  grab & move   : make a fist to drag

Hotkeys:
  q / Esc quit · p pause while the preview window has focus.
  Ctrl+Alt+Q quits · Ctrl+Alt+P pauses globally via Electron/XDG Portal.

No pip, no venv, no PyTorch: the models are small ONNX files executed by the
distro's python3-opencv. See mp_hand.py.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import signal
import sys
import threading
import time
from collections import deque

import numpy as np

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPainter, QColor, QFont
from PyQt6.QtWidgets import QApplication, QWidget

from gestures import DepthHoldDetector, DepthTapDetector, FourFingerScrollDetector
from mapping import camera_point_to_screen, transform_normalized, validate_area
from smart_context import SmartCopyPasteContext
from runtime_settings import normalize_updates, values_from_args

HERE = pathlib.Path(__file__).resolve().parent
PALM_MODEL = HERE / "palm_detection_mediapipe_2023feb.onnx"
HAND_MODEL = HERE / "handpose_estimation_mediapipe_2023feb.onnx"

# 21-keypoint hand layout (MediaPipe convention)
WRIST = 0
THUMB_MCP, THUMB_TIP = 2, 4
INDEX_MCP, INDEX_TIP = 5, 8
MIDDLE_MCP, MIDDLE_TIP = 9, 12
RING_MCP, RING_TIP = 13, 16
PINKY_MCP, PINKY_TIP = 17, 20
FINGER_TIPS = (INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP)
FINGER_PIPS = (6, 10, 14, 18)
PALM_MCPS = (INDEX_MCP, MIDDLE_MCP, RING_MCP, PINKY_MCP)


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
        self._uinput_cls = UInput
        self.keyboard = None
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
                "Run ./setup.sh first (installs a session-scoped udev "
                "uaccess rule), then launch via ./run.sh.")
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

    def scroll(self, steps):
        """Emit discrete vertical wheel ticks; positive scrolls up."""
        steps = int(steps)
        if steps == 0:
            return
        self.ui.write(self.e.EV_REL, self.e.REL_WHEEL, steps)
        self.ui.syn()

    def _ensure_keyboard(self):
        if self.keyboard is None:
            cap = {
                self.e.EV_KEY: [
                    self.e.KEY_LEFTCTRL,
                    self.e.KEY_C,
                    self.e.KEY_V,
                ]
            }
            self.keyboard = self._uinput_cls(cap, name="mudra-shortcuts")

    def ctrl_shortcut(self, key):
        """Emit only the two keyboard shortcuts Mudra intentionally supports."""
        code = {"c": self.e.KEY_C, "v": self.e.KEY_V}.get(key)
        if code is None:
            raise ValueError("Mudra only emits Ctrl+C and Ctrl+V")
        self._ensure_keyboard()
        self.keyboard.write(self.e.EV_KEY, self.e.KEY_LEFTCTRL, 1)
        self.keyboard.write(self.e.EV_KEY, code, 1)
        self.keyboard.syn()
        time.sleep(0.015)
        self.keyboard.write(self.e.EV_KEY, code, 0)
        self.keyboard.write(self.e.EV_KEY, self.e.KEY_LEFTCTRL, 0)
        self.keyboard.syn()

    def close(self):
        for dev in (self.keyboard, self.ui):
            if dev is None:
                continue
            try:
                dev.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Commands from the Electron launcher.  The launcher owns global shortcuts via
# the Wayland GlobalShortcuts portal and writes only the allow-listed commands
# below to this pipe.  Python never opens /dev/input/event*.
# ---------------------------------------------------------------------------
class ControlChannel:
    ALLOWED = {"pause", "quit"}

    def __init__(self, enabled):
        self.fd = None
        self._buf = b""
        if not enabled:
            return
        try:
            self.fd = sys.stdin.fileno()
            os.set_blocking(self.fd, False)
        except (AttributeError, OSError, ValueError):
            self.fd = None

    def poll(self):
        if self.fd is None:
            return []

        while True:
            try:
                chunk = os.read(self.fd, 4096)
            except BlockingIOError:
                break
            except OSError:
                self.fd = None
                break
            if not chunk:
                self.fd = None
                break
            self._buf += chunk
            if len(self._buf) > 16384:
                self._buf = self._buf[-16384:]

        if b"\n" not in self._buf:
            return []

        lines = self._buf.split(b"\n")
        self._buf = lines.pop()
        out = []
        for line in lines:
            command = line.decode("utf-8", errors="ignore").strip()
            if not command:
                continue
            if command in self.ALLOWED:
                out.append(command)
                continue
            if command.startswith("{"):
                try:
                    message = json.loads(command)
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if (isinstance(message, dict)
                        and message.get("type") in ("setting", "settings")):
                    out.append(message)
        return out


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


def _finger_depth(kp, tip, base, hand_scale):
    """Depth of one fingertip relative to its base, normalized by hand size."""
    if kp.shape[1] < 3:
        return 0.0
    return float((kp[tip, 2] - kp[base, 2]) / max(hand_scale, 1e-3))


def _orient_frame(frame, rotate, mirror_x, mirror_y):
    """Transform preview pixels exactly like cursor coordinates."""
    import cv2
    if rotate == 90:
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    elif rotate == 180:
        frame = cv2.rotate(frame, cv2.ROTATE_180)
    elif rotate == 270:
        frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    if mirror_x:
        frame = cv2.flip(frame, 1)
    if mirror_y:
        frame = cv2.flip(frame, 0)
    return frame


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
    def __init__(self, model, cap, mouse, control, args):
        super().__init__()
        self.model, self.cap, self.mouse = model, cap, mouse
        self.control = control
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
        self._kp_preview = None
        self.index_tap = DepthTapDetector(
            args.tap_lift, args.tap_return, args.tap_cooldown)
        self.ring_tap = DepthTapDetector(
            args.tap_lift, args.tap_return, args.tap_cooldown)
        self.pinky_tap = DepthTapDetector(
            args.tap_lift, args.tap_return, args.tap_cooldown)
        self.thumb_drag = DepthHoldDetector(
            args.thumb_lift, args.thumb_return)
        self.four_finger_scroll = FourFingerScrollDetector(
            rest_threshold=args.scroll_rest,
            start_delta=args.scroll_start,
            speed=args.scroll_speed,
            release_timeout=args.scroll_release,
            invert=args.invert_scroll)
        self.smart_context = SmartCopyPasteContext(
            enabled=args.smart_pinky, max_nodes=args.atspi_max_nodes)
        self.runtime_settings = values_from_args(args)
        self.setWindowTitle(f"mudra — {args.mode} mode")
        self.resize(560, 420)
        self.show()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(2)

    def _reset_desk_gestures(self):
        self.index_tap.reset()
        self.ring_tap.reset()
        self.pinky_tap.reset()
        self.thumb_drag.reset()
        self.four_finger_scroll.reset()

    def _release_left(self):
        if self.left_down:
            self.mouse.release("left")
            self.left_down = False
        self.grabbing = False

    def _apply_runtime_updates(self, updates):
        """Validate and apply dashboard settings without restarting Mudra."""
        try:
            accepted = normalize_updates(self.runtime_settings, updates)
        except (KeyError, TypeError, ValueError) as exc:
            print(f"Dashboard setting rejected: {exc}", file=sys.stderr)
            return False

        if not accepted:
            return True

        self.runtime_settings.update(accepted)
        for key, value in accepted.items():
            setattr(self.args, key, value)

        changed = set(accepted)

        if changed & {"tap_lift", "tap_return", "tap_cooldown"}:
            self.index_tap = DepthTapDetector(
                self.args.tap_lift, self.args.tap_return,
                self.args.tap_cooldown)
            self.ring_tap = DepthTapDetector(
                self.args.tap_lift, self.args.tap_return,
                self.args.tap_cooldown)
            self.pinky_tap = DepthTapDetector(
                self.args.tap_lift, self.args.tap_return,
                self.args.tap_cooldown)

        if changed & {"thumb_lift", "thumb_return"}:
            self.thumb_drag = DepthHoldDetector(
                self.args.thumb_lift, self.args.thumb_return)

        if changed & {
                "scroll_rest", "scroll_start", "scroll_speed",
                "scroll_release", "invert_scroll"}:
            self.four_finger_scroll = FourFingerScrollDetector(
                rest_threshold=self.args.scroll_rest,
                start_delta=self.args.scroll_start,
                speed=self.args.scroll_speed,
                release_timeout=self.args.scroll_release,
                invert=self.args.invert_scroll)

        if "four_finger_scroll" in changed:
            self.four_finger_scroll.reset()

        if "smart_pinky" in changed:
            self.smart_context.enabled = self.args.smart_pinky

        if "median" in changed:
            old = list(self._hist)[-self.args.median:]
            self._hist = deque(old, maxlen=self.args.median)

        if changed & {"mincutoff", "beta"}:
            self.fx = OneEuro(
                mincutoff=self.args.mincutoff, beta=self.args.beta)
            self.fy = OneEuro(
                mincutoff=self.args.mincutoff, beta=self.args.beta)
            self._hist.clear()

        if "conf" in changed:
            self.model.landmarker.conf_threshold = self.args.conf

        self.status = "settings updated"
        return True

    def _handle_control_message(self, message):
        if message.get("type") == "setting":
            key = message.get("key")
            if isinstance(key, str):
                self._apply_runtime_updates({key: message.get("value")})
        elif message.get("type") == "settings":
            values = message.get("values")
            if isinstance(values, dict):
                self._apply_runtime_updates(values)

    def _toggle_pause(self):
        self.paused = not self.paused
        self._release_left()
        self._reset_desk_gestures()

    def tick(self):
        for command in self.control.poll():
            if isinstance(command, dict):
                self._handle_control_message(command)
                continue
            if command == "quit":
                self.quit()
                return
            if command == "pause":
                self._toggle_pause()
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
                self._reset_desk_gestures()
        self._draw(frame, kp)

    def _handle_hand(self, kp, conf, shape, now):
        if self.args.mode == "desk":
            self._handle_desk_hand(kp, conf, shape, now)
        else:
            self._handle_air_hand(kp, conf, shape, now)

    def _handle_desk_hand(self, kp, conf, shape, now):
        h, w = shape[:2]

        # MediaPipe already predicts relative Z. Normalize each fingertip's Z
        # against its MCP and the hand's X/Y size, so moving the whole hand up
        # or down does not look like a click.
        scale = max(_dist(kp[INDEX_MCP], kp[PINKY_MCP]),
                    _dist(kp[WRIST], kp[MIDDLE_MCP])) + 1e-3
        index_z = _finger_depth(kp, INDEX_TIP, INDEX_MCP, scale)
        middle_z = _finger_depth(kp, MIDDLE_TIP, MIDDLE_MCP, scale)
        ring_z = _finger_depth(kp, RING_TIP, RING_MCP, scale)
        thumb_z = _finger_depth(kp, THUMB_TIP, THUMB_MCP, scale)
        pinky_z = _finger_depth(kp, PINKY_TIP, PINKY_MCP, scale)

        # Four-finger scrolling is intentionally evaluated before cursor/click
        # actions. Only the four non-thumb fingers participate: when all four
        # remain near their learned desk plane and move coherently vertically,
        # cursor motion and all click/drag gestures are suppressed.
        scroll_points = []
        for tip in (INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP):
            scroll_points.append(transform_normalized(
                kp[tip][0] / w, kp[tip][1] / h,
                self.args.rotate, self.args.mirror_x, self.args.mirror_y))
        scrolling, wheel_steps = self.four_finger_scroll.update(
            scroll_points, (index_z, middle_z, ring_z, pinky_z), now)

        if self.args.four_finger_scroll and scrolling:
            if self.left_down:
                self.mouse.release("left")
                self.left_down = False
            self.grabbing = False

            # Prevent a four-finger swipe from becoming clicks/copy/paste when
            # the scroll gesture ends. Those detectors relearn their rest plane
            # after scrolling instead.
            self.index_tap.reset()
            self.ring_tap.reset()
            self.pinky_tap.reset()
            self.thumb_drag.reset()
            self._hist.clear()

            if not self.paused and wheel_steps:
                self.mouse.scroll(wheel_steps)
            self.status = (
                f"SCROLL {'up' if wheel_steps > 0 else 'down' if wheel_steps < 0 else ''}"
            ).rstrip()
            return

        # The middle fingertip is the normal cursor anchor. It can stay resting
        # on the desk while the remaining fingers act as dedicated controls.
        tx, ty = camera_point_to_screen(
            kp[MIDDLE_TIP][0], kp[MIDDLE_TIP][1], w, h, self.args.area,
            self.args.rotate, self.args.mirror_x, self.args.mirror_y)
        self._hist.append((tx, ty))
        mx = float(np.median([p[0] for p in self._hist]))
        my = float(np.median([p[1] for p in self._hist]))
        pos = np.array([self.fx(mx, now), self.fy(my, now)])
        if not self.paused:
            self.mouse.move_to(pos)

        index_click = self.index_tap.update(index_z, now)
        ring_click = self.ring_tap.update(ring_z, now)
        pinky_action = self.pinky_tap.update(pinky_z, now)
        drag_active, drag_changed = self.thumb_drag.update(thumb_z)

        if not self.paused:
            if drag_changed:
                if drag_active and not self.left_down:
                    self.mouse.press("left")
                    self.left_down = True
                elif not drag_active and self.left_down:
                    self.mouse.release("left")
                    self.left_down = False
            self.grabbing = drag_active

            if not drag_active and index_click:
                self.mouse.click("left")
                self.status = "LEFT CLICK (index)"
            elif not drag_active and ring_click:
                self.mouse.click("right")
                self.status = "RIGHT CLICK (ring)"
            elif pinky_action and not drag_active:
                action, reason = self.smart_context.decide()
                if action == "copy":
                    self.mouse.ctrl_shortcut("c")
                    self.status = "COPY (pinky)"
                elif action == "paste":
                    self.mouse.ctrl_shortcut("v")
                    self.status = "PASTE (pinky)"
                else:
                    self.status = f"PINKY: {reason}"
            elif drag_active:
                self.status = "DRAG (thumb lifted)"
            else:
                self.status = "desk track — middle finger cursor"
        else:
            self.grabbing = False

    def _handle_air_hand(self, kp, conf, shape, now):
        h, w = shape[:2]
        left, top, right, bottom = self.args.area
        area_w = max(1e-3, right - left)
        area_h = max(1e-3, bottom - top)

        # Legacy pinch distances for the original front-facing air mode.
        scale = max(_dist(kp[INDEX_MCP], kp[PINKY_MCP]),
                    _dist(kp[WRIST], kp[MIDDLE_MCP])) + 1e-3
        self._di.append(_dist(kp[THUMB_TIP], kp[INDEX_TIP]) / scale)
        self._dm.append(_dist(kp[THUMB_TIP], kp[MIDDLE_TIP]) / scale)
        d_index = float(np.median(self._di))
        d_middle = float(np.median(self._dm))
        on, off = self.args.pinch, self.args.pinch + 0.18

        fist_now = self.args.grab and _curled_count(kp) >= 3
        if fist_now == self._fist_on:
            self._fist_flip = 0
        else:
            self._fist_flip += 1
            if self._fist_flip >= 2:
                self._fist_on = fist_now
                self._fist_flip = 0
        fist = self._fist_on

        if fist and not self.grabbing:
            self.grabbing = True
            self._grab_c0 = self.mouse.pos.copy()
            c = _palm_center(kp)
            ax, ay = transform_normalized(
                c[0] / w, c[1] / h, self.args.rotate,
                self.args.mirror_x, self.args.mirror_y)
            self._grab_a0 = np.array([ax, ay])
            self._hist.clear()
        elif not fist and self.grabbing:
            self.grabbing = False

        if self.grabbing:
            c = _palm_center(kp)
            ax, ay = transform_normalized(
                c[0] / w, c[1] / h, self.args.rotate,
                self.args.mirror_x, self.args.mirror_y)
            delta = np.array([
                (ax - self._grab_a0[0]) / area_w,
                (ay - self._grab_a0[1]) / area_h,
            ])
            tgt = self._grab_c0 + delta
            pos = np.array([self.fx(float(np.clip(tgt[0], 0, 1)), now),
                            self.fy(float(np.clip(tgt[1], 0, 1)), now)])
            if not self.paused:
                self.mouse.move_to(pos)
            pointing = True
        else:
            pointing = conf[INDEX_TIP] >= 0.2 and d_index > off
            if pointing:
                tx, ty = camera_point_to_screen(
                    kp[INDEX_TIP][0], kp[INDEX_TIP][1], w, h, self.args.area,
                    self.args.rotate, self.args.mirror_x, self.args.mirror_y)
                self._hist.append((tx, ty))
                mx = float(np.median([p[0] for p in self._hist]))
                my = float(np.median([p[1] for p in self._hist]))
                pos = np.array([self.fx(mx, now), self.fy(my, now)])
                if not self.paused:
                    self.mouse.move_to(pos)

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
        disp = _orient_frame(
            frame, self.args.rotate, self.args.mirror_x, self.args.mirror_y)
        disp = cv2.cvtColor(disp, cv2.COLOR_BGR2RGB)
        self._qbuf = np.ascontiguousarray(disp)
        h, w, _ = self._qbuf.shape
        self._qimg = QImage(self._qbuf.data, w, h, 3 * w,
                            QImage.Format.Format_RGB888)
        self._kp_preview = None
        if kp is not None:
            raw_h, raw_w = frame.shape[:2]
            mk = np.zeros((len(kp), 2), dtype=np.float32)
            for i, point in enumerate(kp):
                nx, ny = transform_normalized(
                    point[0] / raw_w, point[1] / raw_h,
                    self.args.rotate, self.args.mirror_x, self.args.mirror_y)
                mk[i] = (nx * w, ny * h)
            self._kp_preview = (mk, w, h)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        if self._qbuf is not None:
            p.drawImage(self.rect(), self._qimg)

            if self.args.mode == "desk":
                left, top, right, bottom = self.args.area
                p.setPen(QColor(80, 190, 255))
                x = int(left * self.width())
                y = int(top * self.height())
                rw = int((right - left) * self.width())
                rh = int((bottom - top) * self.height())
                p.drawRect(x, y, rw, rh)

            if self._kp_preview is not None:
                mk, fw, fh = self._kp_preview
                sx, sy = self.width() / fw, self.height() / fh

                def pt(i):
                    return int(mk[i][0] * sx), int(mk[i][1] * sy)

                p.setPen(QColor(255, 200, 0))
                for i in (THUMB_TIP, INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP):
                    x, y = pt(i)
                    radius = 9 if i == MIDDLE_TIP and self.args.mode == "desk" else 6
                    p.drawEllipse(x - radius, y - radius, radius * 2, radius * 2)

        p.setPen(QColor(255, 255, 0))
        p.setFont(QFont("sans", 11))
        tag = "PAUSED" if self.paused else self.status
        p.drawText(8, 22, f"mudra {self.args.mode} | {self.fps:4.1f} fps | {tag}")
        p.setPen(QColor(160, 160, 160))
        if self.args.mode == "desk":
            help_text = ("middle=cursor · index=L · ring=R · thumb=drag · "
                         "pinky=copy/paste · 4 fingers=scroll · p pause")
        else:
            help_text = ("index=cursor · fist=grab · thumb+middle=L · "
                         "thumb+index=R · p pause")
        p.drawText(8, self.height() - 10, help_text)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_P:
            self._toggle_pause()
        elif e.key() in (Qt.Key.Key_Q, Qt.Key.Key_Escape):
            self.quit()

    def quit(self):
        self.timer.stop()
        self._release_left()
        self.cap.release()
        self.mouse.close()
        QApplication.instance().quit()


def build_args():
    p = argparse.ArgumentParser(
        description="mudra — overhead desk hand-mouse / air-mouse.")
    p.add_argument("--camera", type=int, default=0)
    p.add_argument("--mode", choices=("desk", "air"), default="desk",
                   help="desk = overhead middle-finger cursor (default); "
                        "air = original front-facing index-pointer mode")
    p.add_argument("--rotate", type=int, choices=(0, 90, 180, 270), default=0,
                   help="rotate camera coordinates clockwise before mapping")
    p.add_argument("--mirror-x", action=argparse.BooleanOptionalAction,
                   default=None,
                   help="mirror left/right after rotation; defaults on in air "
                        "mode and off in desk mode")
    p.add_argument("--mirror-y", action=argparse.BooleanOptionalAction,
                   default=False,
                   help="mirror top/bottom after rotation")
    p.add_argument("--area", nargs=4, type=float,
                   metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"),
                   help="active camera rectangle in normalized oriented "
                        "coordinates, e.g. --area 0.10 0.08 0.90 0.92")
    p.add_argument("--margin", type=float, default=None,
                   help="symmetric active-area margin shorthand; desk default "
                        "0.10, air default 0.15")
    p.add_argument("--conf", type=float, default=0.8,
                   help="hand confidence threshold")
    p.add_argument("--pinch", type=float, default=0.62,
                   help="air mode pinch threshold")
    p.add_argument("--no-grab", dest="grab", action="store_false", default=True,
                   help="air mode: disable fist-to-grab")
    p.add_argument("--tap-lift", type=float, default=0.14,
                   help="desk mode: normalized Z excursion that arms a finger tap")
    p.add_argument("--tap-return", type=float, default=0.055,
                   help="desk mode: return-to-desk threshold that fires the tap")
    p.add_argument("--tap-cooldown", type=float, default=0.22,
                   help="desk mode: minimum seconds between taps per finger")
    p.add_argument("--thumb-lift", type=float, default=0.16,
                   help="desk mode: thumb Z excursion that starts drag")
    p.add_argument("--thumb-return", type=float, default=0.065,
                   help="desk mode: thumb return threshold that drops")
    p.add_argument("--four-finger-scroll",
                   action=argparse.BooleanOptionalAction, default=True,
                   help="desk mode: scroll when index/middle/ring/pinky rest "
                        "on the desk and move vertically together")
    p.add_argument("--scroll-rest", type=float, default=0.085,
                   help="desk mode: max normalized Z deviation for each of the "
                        "four scrolling fingers to count as resting")
    p.add_argument("--scroll-start", type=float, default=0.006,
                   help="desk mode: normalized vertical movement needed to "
                        "enter four-finger scrolling")
    p.add_argument("--scroll-speed", type=float, default=95.0,
                   help="desk mode: wheel ticks per normalized camera-distance")
    p.add_argument("--scroll-release", type=float, default=0.16,
                   help="desk mode: idle seconds before leaving scroll mode")
    p.add_argument("--invert-scroll", action="store_true",
                   help="invert four-finger vertical scrolling direction")
    p.add_argument("--smart-pinky", action=argparse.BooleanOptionalAction,
                   default=True,
                   help="desk mode: context-aware pinky copy/paste via AT-SPI")
    p.add_argument("--atspi-max-nodes", type=int, default=2500,
                   help="maximum accessibility nodes inspected per pinky action")
    p.add_argument("--median", type=int, default=3,
                   help="frames of cursor median filtering")
    p.add_argument("--mincutoff", type=float, default=1.0,
                   help="One-Euro: lower = steadier when holding still")
    p.add_argument("--beta", type=float, default=0.05,
                   help="One-Euro: higher = snappier on fast moves")
    p.add_argument("--control-stdin", action="store_true",
                   help=argparse.SUPPRESS)
    args = p.parse_args()

    if args.mirror_x is None:
        args.mirror_x = args.mode == "air"

    if args.margin is None:
        args.margin = 0.10 if args.mode == "desk" else 0.15
    if not 0.0 <= args.margin < 0.5:
        p.error("--margin must be >= 0 and < 0.5")

    if args.area is None:
        m = args.margin
        args.area = (m, m, 1.0 - m, 1.0 - m)
    else:
        args.area = tuple(args.area)

    try:
        validate_area(args.area)
    except ValueError as exc:
        p.error(str(exc))

    if not (0 < args.tap_return < args.tap_lift):
        p.error("--tap-return must be > 0 and smaller than --tap-lift")
    if not (0 < args.thumb_return < args.thumb_lift):
        p.error("--thumb-return must be > 0 and smaller than --thumb-lift")
    return args


def main():
    args = build_args()
    for m in (PALM_MODEL, HAND_MODEL):
        if not m.exists():
            sys.exit(f"Missing hand model: {m}\nRun ./setup.sh to fetch it.")

    print(f"inference=OpenCV-dnn (CPU)  pointer=absolute (uinput tablet)  "
          f"mode={args.mode} rotate={args.rotate} mirror_x={args.mirror_x} "
          f"mirror_y={args.mirror_y} area={args.area}")
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
    control = ControlChannel(args.control_stdin)
    if not args.control_stdin:
        print("NOTE: global shortcuts are disabled when mudra.py is run directly; "
              "use ./run.sh for Electron/XDG Portal hotkeys.")
    mouse = VirtualMouse()
    win = HandMouse(model, cap, mouse, control, args)  # noqa: F841
    signal.signal(signal.SIGINT, lambda *_: win.quit())
    if args.mode == "desk":
        print("mudra desk mode: middle=cursor; index=left; ring=right; "
              "thumb=drag; pinky=copy/paste; four fingers=scroll.")
    else:
        print("mudra air mode: point with index; pinch to click; fist to grab.")
    rc = app.exec()
    print("\nbye.")
    sys.exit(rc)


if __name__ == "__main__":
    main()
