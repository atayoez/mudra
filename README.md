# mudra

**Replace the mouse with your hand and an overhead webcam on Linux/Wayland.**

`mudra` now defaults to **desk mode**: mount the camera above your hand,
roughly perpendicular to the desk. Your middle fingertip becomes the pointer
anchor and the other fingers act as dedicated mouse controls. MediaPipe hand
landmarks run locally through OpenCV DNN and pointer/shortcut events are
injected through `/dev/uinput`.

The original front-facing air-mouse is still available with `--mode air`.

Global keyboard shortcuts are handled separately by a pinned Electron helper
through the Wayland **XDG GlobalShortcuts portal**. The Python process never
opens physical `/dev/input/event*` keyboard devices.

## Desk mode

Mount the webcam above the desk so it can see the whole hand. The default
control layout is intentionally designed so the **middle finger can stay
resting and steady** while the other fingers perform actions:

| Finger | Action |
|---|---|
| **Middle finger** | absolute cursor position |
| **Index finger** | lift/tap → left click |
| **Ring finger** | lift/tap → right click |
| **Thumb** | lift and hold → drag; return to the desk → drop |
| **Little finger** | context-aware copy/paste |
| **Index + middle + ring + little together** | four-finger vertical scroll |

### Four-finger scrolling

Put **all four non-thumb fingers** on the desk and move them together vertically,
similar to a multi-finger touchpad gesture. The thumb is intentionally ignored
by scroll recognition.

Mudra enters scroll mode only when:

- index, middle, ring and little finger are all near their learned resting
  depth on the desk,
- all four fingertips move coherently in the same vertical direction,
- vertical movement clearly dominates horizontal movement.

While scrolling, normal middle-finger cursor motion, left/right clicks,
copy/paste and thumb drag are suppressed. This prevents a scroll gesture from
also moving the cursor or clicking.

Finger movement upward emits wheel-up events; downward emits wheel-down events.
Reverse that behavior with:

```bash
./run.sh --invert-scroll
```

Useful tuning options:

```bash
./run.sh --scroll-speed 95
./run.sh --scroll-start 0.006
./run.sh --scroll-rest 0.085
./run.sh --scroll-release 0.16
```

Disable the gesture entirely with:

```bash
./run.sh --no-four-finger-scroll
```

The index/ring/thumb/little-finger actions use the MediaPipe model's relative
**Z/depth estimate**, not just 2D movement. Each finger learns its own resting
depth, so small changes in camera height or moving the whole hand should not be
interpreted as clicks.

The active part of the camera image is mapped to the whole screen. A blue
rectangle in the preview shows that region.

### Smart little-finger copy/paste

A little-finger tap asks the Linux AT-SPI accessibility layer for **state only**:

- focused context has a selection → **Copy** (`Ctrl+C`)
- focused control is editable and has no selection → **Paste** (`Ctrl+V`)
- neither condition is known → **do nothing**

Mudra does **not** call AT-SPI APIs that retrieve the selected text contents.
It only checks focus/editable state and the number of selections.

This is deliberately conservative. If an application does not expose usable
AT-SPI state, the pinky gesture becomes a no-op instead of blindly sending a
shortcut (important for terminals, where an accidental `Ctrl+C` could stop a
process).

Disable it with:

```bash
./run.sh --no-smart-pinky
```

### Camera orientation and desk area

If the camera is mounted in another orientation:

```bash
./run.sh --rotate 90
./run.sh --rotate 180
./run.sh --mirror-x
./run.sh --mirror-y
```

Restrict the usable desk rectangle without physically moving the camera:

```bash
./run.sh --area 0.10 0.08 0.90 0.92
```

The values are normalized `LEFT TOP RIGHT BOTTOM`; that rectangle maps to
the full desktop.

### Depth tuning

Defaults are intended as a starting point because webcams and hand angles
differ:

```bash
./run.sh --tap-lift 0.14 --tap-return 0.055
./run.sh --thumb-lift 0.16 --thumb-return 0.065
./run.sh --scroll-start 0.006 --scroll-speed 95
```

Increase the `*-lift` values if gestures trigger too easily. Decrease them if
a deliberate lift is not detected. The return threshold must stay lower than
its corresponding lift threshold.

### Legacy air mode

```bash
./run.sh --mode air
```

Air mode keeps the previous index-pointer, pinch-click and fist-drag behavior.

## Hotkeys

When the preview window has focus:

- **P** — pause/resume
- **Q** or **Esc** — quit
- **Ctrl+C** in the launching terminal — quit

Global shortcuts, even when another application has focus:

- **Ctrl+Alt+P** — pause/resume
- **Ctrl+Alt+Q** — quit

On GNOME/Wayland, the desktop normally shows a consent dialog the first time
Mudra requests its global shortcuts. Accepting it persists the bindings for
the installed Mudra desktop identity. KDE Plasma generally exposes the
bindings through System Settings instead of showing the same dialog.

Mudra pins **Electron 45.0.0-alpha.14** exactly. That Electron alpha submits
the shortcuts through the portal, but does not yet expose the portal's final
asynchronous accept/deny result to JavaScript. Mudra therefore treats the
initial registration result only as a submission result and remains usable
with its focused-window shortcuts if global binding is denied.

## Security model

The installer intentionally avoids the broad Linux `input` group.

- Python uses `python-evdev` only to create the virtual `uinput` pointer.
- Python does **not** enumerate or read physical keyboard event devices.
- `/dev/uinput` gets `TAG+="uaccess"`; systemd-logind grants access to the
  active local desktop session instead of permanently granting raw input
  access to the account.
- Electron receives global shortcuts from the desktop portal and sends only
  the allow-listed commands `pause` and `quit` to Python over stdin.
- Python arguments are serialized as JSON rather than interpolated into a
  shell command.
- The two OpenCV ONNX models are pinned to OpenCV Model Zoo commit
  `47534e27c9851bb1128ccc0102f1145e27f23f98` and SHA-256 verified before
  use.
- The Electron package version is exact-pinned and verified after npm install.

If an older Mudra setup previously added your account to the `input` group,
the new setup prints a warning. It does not automatically remove that
membership because another application may rely on it. If Mudra was the only
reason you joined that group, remove it and log out/in:

```bash
sudo gpasswd -d "$USER" input
```

## Requirements

- Linux with Wayland; Ubuntu 26.04/GNOME is a primary target.
- A webcam.
- Python 3 with OpenCV, NumPy, python-evdev, PyQt6 and pyatspi.
- Node.js + npm for the pinned Electron launcher.
- systemd-logind/udev `uaccess` support for session-scoped `/dev/uinput`
  access.

`setup.sh` installs distro packages for Debian/Ubuntu, Fedora, Arch and
openSUSE when their supported package managers are available.

## Install

```bash
git clone https://github.com/crakxx/mudra.git
cd mudra
./setup.sh
```

The privileged phase only installs distro packages, loads `uinput`, and
installs the narrow udev rule. Electron, the desktop launcher and the model
files are installed/downloaded as your normal user.

The setup also installs:

- `~/.local/bin/mudra`
- `~/.local/share/applications/io.github.crakxx.mudra.desktop`

That reverse-DNS desktop identity is important on GNOME because the
GlobalShortcuts portal rejects unidentifiable host applications.

## Run

```bash
./run.sh
```

Beim normalen Start öffnet Electron zusätzlich das lokale **Mudra-Dashboard**.
Die Handsteuerung läuft weiter, wenn das Dashboard-Fenster geschlossen wird.

### Barrierearmes Einstellungs-Dashboard

Das Dashboard ist bewusst für gute Lesbarkeit ausgelegt:

- **sehr große Standardschrift** und drei wählbare Textgrößen,
- hoher Hell-Dunkel-Kontrast ohne Informationen nur über Farbe zu vermitteln,
- große Klick-/Touch-Ziele und deutlich sichtbare Tastatur-Fokusrahmen,
- vollständige Bedienung mit Tab, Shift+Tab, Pfeiltasten, Enter und Leertaste,
- exakte Zahlenfelder zusätzlich zu den Schiebereglern,
- klare Gruppen für Klicks, Drag & Drop, Scrollen, Zeiger und Funktionen,
- für jeden Zahlenwert eine Erklärung für **kleinere** und **größere** Werte,
- verständliche Fehlermeldungen, wenn zwei Werte nicht zusammenpassen.

Die Werte werden **live** an den laufenden Python-Prozess übertragen und unter
Electron lokal gespeichert. Ein Neustart ist zum Feinabstimmen nicht nötig.

Explizite Startparameter überschreiben beim Start den gespeicherten Wert, z. B.:

```bash
./run.sh --scroll-speed 120
```

Das Dashboard kann nur eine feste Allowlist von Mudra-Einstellungen ändern.
Es kann keine beliebigen Shell-Befehle an Python schicken. Der Electron-Renderer
läuft außerdem mit:

```text
contextIsolation = true
nodeIntegration  = false
sandbox          = true
```

und einer Content-Security-Policy ohne Netzwerkzugriff (`connect-src 'none'`).

Mit **„Alle Werte auf Standard zurücksetzen“** lassen sich die empfohlenen
Startwerte jederzeit wiederherstellen.

Running `python3 mudra.py` directly is still possible, but global portal
shortcuts and the Electron settings dashboard are intentionally disabled in
that mode.

### General tuning

```bash
./run.sh --margin 0.08     # larger active camera area
./run.sh --median 5        # steadier cursor
./run.sh --mincutoff 0.7   # steadier while holding still
./run.sh --beta 0.09       # snappier fast movement
./run.sh --conf 0.6        # keep tracking harder poses
```

## Architecture

```text
                         XDG GlobalShortcuts portal
                         ┌─────────────────────────┐
Ctrl+Alt+P / Ctrl+Alt+Q ─▶ Electron 45 alpha      │
                         └───────────┬─────────────┘
                                     │ allow-listed
                                     │ pause / quit
                                     ▼
overhead webcam ─▶ OpenCV DNN ─▶ 21 hand landmarks (X/Y/Z)
                                      │
                         ┌────────────┼──────────────┐
                         ▼            ▼              ▼
                  middle finger   depth gestures   pinky context
                    X/Y cursor     clicks/drag       AT-SPI state
                         │
                         └──── four resting fingers ────▶ scroll
                         └────────────┬──────────────┘
                                      ▼
                                /dev/uinput
                                     │
                                     ▼
                             Wayland compositor
```

The camera frames and hand landmarks stay local. There is no runtime network
code in the Python application.

## Model provenance

The downloaded model payloads are verified against the Git LFS SHA-256 object
IDs published by OpenCV Model Zoo:

```text
palm_detection_mediapipe_2023feb.onnx
78ff51c38496b7fc8b8ebdb6cc8c1abb02fa6c38427c6848254cdaba57fcce7c

handpose_estimation_mediapipe_2023feb.onnx
db0898ae717b76b075d9bf563af315b29562e11f8df5027a1ef07b02bef6d81c
```

## Development checks

The lightweight security/syntax checks do not need the models or Electron
runtime:

```bash
./tests/security-smoke.sh
```

## Credits and license

- Hand models: MediaPipe palm detection and hand landmarks from
  [OpenCV Model Zoo](https://github.com/opencv/opencv_zoo), Apache-2.0.
- Original MediaPipe models: Google MediaPipe, Apache-2.0.
- `mp_hand.py` adapts OpenCV Model Zoo pre/post-processing.

Mudra is licensed **AGPL-3.0**; see [LICENSE](LICENSE).
