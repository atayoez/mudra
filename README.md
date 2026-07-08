# mudra

**Control your mouse with hand gestures, using just a webcam.**

`mudra` is a webcam "air-mouse" for Linux/Wayland. MediaPipe hand models
(21 keypoints, run by OpenCV — no PyTorch, no pip) track your hand in real
time and drive the system cursor: point to move, pinch to click, make a fist
to grab and drag. Cursor and clicks are injected through a virtual
`evdev`/`uinput` device, so it works **natively on Wayland** (where X11 tools
like `xdotool`/`pyautogui` can't move the real cursor).

> The name comes from *mudrā* — a symbolic hand gesture/pose.

## Gestures

| Gesture | Action |
|---|---|
| ☝️ point with your **index finger** | move the cursor (the fingertip is the pointer) |
| 🤏 pinch **thumb + middle** | left click — hold to **drag** |
| 🤙 pinch **thumb + index** | right click |
| ✊ make a **fist** | grab & move — holds left button, move your fist to drag, open your hand to drop |

Hotkeys (read globally from the keyboard, so they work regardless of window
focus): **`q`/`Esc`** quit · **`p`** pause · `Ctrl+C` quits.

## No pip, no venv, no PyTorch

Everything runs on **distro packages alone**: the MediaPipe palm-detection and
hand-landmark models (two ONNX files, ~8 MB total, from the [OpenCV Model
Zoo](https://github.com/opencv/opencv_zoo)) are executed by your distro's
`python3-opencv` via `cv2.dnn`. Real-time on CPU (~15–30 ms/frame) — no GPU
needed. This also avoids the MediaPipe pip package entirely, which ships no
wheel for Python 3.13 / aarch64.

## Requirements

- Linux on Wayland, any distro. `setup.sh` knows the package names for
  openSUSE, Debian/Ubuntu, Fedora and Arch; others need a one-time manual
  package install.
- Python 3, a webcam, and access to `/dev/uinput`.

## Install

```bash
git clone https://github.com/atayozcan/mudra.git
cd mudra
./setup.sh
```

One script does everything: system packages + `/dev/uinput` access (elevating
itself with `pkexec`/`sudo` — asks for your password), then the two hand
models (~8 MB) as your user.

`setup.sh` supports openSUSE (`zypper`), Debian/Ubuntu (`apt`), Fedora (`dnf`)
and Arch (`pacman`). On other distros install the equivalents manually
(python3, OpenCV python bindings, NumPy, python-evdev, PyQt6, the Qt6 Wayland
plugin), then re-run `setup.sh` — it still sets up the udev rule and
`/dev/uinput` access.

## Run

```bash
./run.sh
```

A small camera-preview window opens; point with your index finger to take over
the cursor.

### Tuning

```bash
./run.sh --pinch 0.7      # easier clicks (higher = looser pinch)
./run.sh --margin 0.1     # bigger active box (less arm travel, less jitter)
./run.sh --mincutoff 0.7  # smoother/steadier cursor (a touch more lag)
./run.sh --beta 0.09      # snappier on fast moves
./run.sh --median 5       # steadier cursor (more smoothing lag)
./run.sh --conf 0.6       # keep tracking harder hand poses (more false hits)
./run.sh --no-grab        # disable fist-to-grab
```

## How it works

```
webcam ─▶ MediaPipe palm detection + hand landmarks (21 keypoints,
          two ONNX models via OpenCV dnn, CPU)
       ─▶ gesture logic: index fingertip → cursor;
          thumb–finger pinch distances → clicks; curled fingers → fist-grab
       ─▶ median filter + One-Euro smoothing
       ─▶ evdev/uinput virtual tablet (absolute pointer events)
```

- **Tracking, not just detecting:** like the real MediaPipe pipeline, the palm
  detector only runs to (re)acquire the hand; while tracking, each frame's
  crop comes from the previous frame's landmarks (~2× faster).
- **Low latency:** a capture thread always keeps only the *newest* camera
  frame, so the processing loop never blocks on the camera and never works on
  a stale buffered frame.

- **Smoothing:** a short median filter rejects single-frame keypoint flicker,
  then a [One-Euro filter](https://gery.casiez.net/1euro/) smooths the residual
  tremor — low jitter when holding still, low lag on fast moves.
- **Pinch detection** normalizes thumb-to-finger distance by a rotation-stable
  hand scale, with hysteresis and median smoothing for reliable clicks.
- **Wayland cursor:** the virtual `uinput` device is a tablet-style *absolute*
  pointer (`ABS_X`/`ABS_Y` over a normalized range, like QEMU's usb-tablet),
  so the compositor maps it to the desktop directly — no screen-size
  detection, no drift.

## Credits & license

- Hand models: MediaPipe palm-detection & hand-landmark ONNX from the
  [OpenCV Model Zoo](https://github.com/opencv/opencv_zoo) (Apache-2.0);
  `mp_hand.py` adapts the zoo's reference pre/post-processing.
- Originals: [Google MediaPipe](https://github.com/google-ai-edge/mediapipe)
  (Apache-2.0).

`mudra` itself is licensed **AGPL-3.0** — see [LICENSE](LICENSE).
