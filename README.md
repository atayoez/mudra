# mudra

**Control your mouse with hand gestures, using just a webcam.**

`mudra` is a webcam "air-mouse" for Linux. A YOLO11 hand-pose model tracks your
hand in real time and drives the system cursor: point to move, pinch to click,
make a fist to grab and drag. Cursor and clicks are injected through a virtual
`evdev`/`uinput` device, so it works **natively on Wayland** (where X11 tools
like `xdotool`/`pyautogui` can't move the real cursor) as well as on X11.

> The name comes from *mudrā* — a symbolic hand gesture/pose.

## Gestures

| Gesture | Action |
|---|---|
| ☝️ point with your **index finger** | move the cursor (the fingertip is the pointer) |
| 🤏 pinch **thumb + middle** | left click — hold to **drag** |
| 🤙 pinch **thumb + index** | right click |
| ✊ make a **fist** | grab & move — holds left button, move your fist to drag, open your hand to drop |

Hotkeys (read globally from the keyboard, so they work regardless of window
focus): **`q`/`Esc`** quit · **`p`** pause · **`c`** re-home cursor · `Ctrl+C` quits.

## Why YOLO instead of MediaPipe

MediaPipe Hands — the usual webcam hand tracker — ships **no wheel for Python
3.13 / aarch64**. `mudra` instead runs an [Ultralytics YOLO11n-pose hand
model](https://docs.ultralytics.com/datasets/pose/hand-keypoints/) (21 keypoints)
through PyTorch, on the **GPU** when one is available (CUDA), or CPU otherwise.

## Requirements

- Linux (Wayland or X11). Built and tested on openSUSE Tumbleweed (KDE Plasma,
  Wayland, aarch64) with an NVIDIA GPU, but nothing is Blackwell-specific.
- Python 3.11+ (3.13 supported), a webcam, and access to `/dev/uinput`.
- Optional: an NVIDIA GPU for ~30–45 fps; CPU works but slower.

## Install

```bash
git clone https://github.com/atayozcan/mudra.git
cd mudra

# 1) system packages + /dev/uinput access (asks for your password)
pkexec ./setup.sh

# 2) Python venv (PyTorch + Ultralytics) and the hand model (~6 MB)
./install.sh
```

`setup.sh` is written for openSUSE (`zypper`); on other distros install the
equivalents (python3 + venv, OpenCV python bindings, NumPy, python-evdev, PyQt6,
the Qt6 Wayland plugin) and the udev rule it creates.

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
./run.sh --median 3       # less smoothing lag (3 instead of 5 frames)
./run.sh --imgsz 640      # more accurate keypoints (slower)
./run.sh --no-grab        # disable fist-to-grab
./run.sh --screen 2560x1440   # override detected screen size
```

## How it works

```
webcam ─▶ YOLO11n-pose (21 hand keypoints, GPU)
       ─▶ gesture logic: index fingertip → cursor;
          thumb–finger pinch distances → clicks; curled fingers → fist-grab
       ─▶ median filter + One-Euro smoothing
       ─▶ evdev/uinput virtual mouse (relative events + internal absolute model)
```

- **Smoothing:** a short median filter rejects single-frame keypoint flicker,
  then a [One-Euro filter](https://gery.casiez.net/1euro/) smooths the residual
  tremor — low jitter when holding still, low lag on fast moves.
- **Pinch detection** normalizes thumb-to-finger distance by a rotation-stable
  hand scale, with hysteresis and median smoothing for reliable clicks.
- **Wayland cursor:** an absolute position is emulated with relative `uinput`
  events plus an internal model of the cursor, "homed" to (0,0) once.

## Credits & license

- Hand-pose model: [chrismuntean/YOLO11n-pose-hands](https://github.com/chrismuntean/YOLO11n-pose-hands)
  (trained on Ultralytics' hand-keypoints dataset).
- Inference: [Ultralytics YOLO](https://github.com/ultralytics/ultralytics).

Both Ultralytics and the model are **AGPL-3.0**, so this project is licensed
**AGPL-3.0** as well. See [LICENSE](LICENSE).
