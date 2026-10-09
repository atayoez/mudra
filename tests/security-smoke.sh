#!/bin/bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "== shell syntax =="
bash -n setup.sh
bash -n run.sh

echo "== Python syntax =="
python3 -m py_compile \
    mudra.py mp_hand.py mapping.py gestures.py smart_context.py runtime_settings.py

echo "== pure Python unit tests =="
python3 -m unittest discover -s tests -p 'test_*.py'

echo "== Electron JS syntax =="
node --check electron/main.js
node --check electron/settings.js
node --check electron/preload.js
node --check electron/renderer.js
node tests/dashboard-settings.test.js
node -e 'const p=require("./package.json"); if (p.devDependencies.electron !== "45.0.0-alpha.14") process.exit(1)'

echo "== security invariants =="
if grep -Eq 'InputDevice|list_devices|select\.select' mudra.py; then
    echo "raw keyboard-event listener code reappeared in mudra.py"
    exit 1
fi
if grep -Eq 'usermod[^\n]*input|groupadd[[:space:]]+input' setup.sh; then
    echo "broad input-group provisioning reappeared in setup.sh"
    exit 1
fi
if grep -Fq 'sg input' run.sh || grep -Fq '$*' run.sh; then
    echo "unsafe legacy launcher path reappeared"
    exit 1
fi

grep -Fq 'TAG+="uaccess"' setup.sh
grep -Fq 'io.github.crakxx.mudra.desktop' setup.sh
grep -Fq 'io.github.crakxx.mudra.desktop' electron/main.js
grep -Fq 'shell: false' electron/main.js
grep -Fq 'class ControlChannel' mudra.py
grep -Fq 'MIDDLE_TIP' mudra.py
grep -Fq 'DepthTapDetector' mudra.py
grep -Fq 'FourFingerScrollDetector' mudra.py
grep -Fq 'REL_WHEEL' mudra.py
grep -Fq 'SmartCopyPasteContext' mudra.py
grep -Fq 'normalize_updates' mudra.py
grep -Fq 'contextIsolation: true' electron/main.js
grep -Fq 'nodeIntegration: false' electron/main.js
grep -Fq 'sandbox: true' electron/main.js
grep -Fq "connect-src 'none'" electron/dashboard.html
grep -Fq 'contextBridge.exposeInMainWorld' electron/preload.js
grep -Fq 'font-size: var(--font-size)' electron/dashboard.css
grep -Fq 'outline: 5px solid var(--focus)' electron/dashboard.css
grep -Fq 'getNSelections' smart_context.py
if grep -Eq '\.(getText|getSelection)\(' smart_context.py; then
    echo "smart copy/paste must not read selected text contents"
    exit 1
fi

echo "== supply-chain pins =="
grep -Fq '47534e27c9851bb1128ccc0102f1145e27f23f98' setup.sh
grep -Fq '78ff51c38496b7fc8b8ebdb6cc8c1abb02fa6c38427c6848254cdaba57fcce7c' setup.sh
grep -Fq 'db0898ae717b76b075d9bf563af315b29562e11f8df5027a1ef07b02bef6d81c' setup.sh
if grep -Fq 'opencv_zoo/main/models' setup.sh; then
    echo "unpinned OpenCV main-branch model URL reappeared"
    exit 1
fi

echo "All security smoke checks passed."
