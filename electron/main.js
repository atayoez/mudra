'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { spawn } = require('node:child_process');
const {
  app,
  BrowserWindow,
  globalShortcut,
  ipcMain
} = require('electron');
const {
  SETTINGS,
  defaults,
  applyUpdate,
  applyUpdates,
  fromPythonArgs
} = require('./settings');

const DESKTOP_ID = 'io.github.crakxx.mudra.desktop';
const PAUSE_SHORTCUT = 'Control+Alt+P';
const QUIT_SHORTCUT = 'Control+Alt+Q';
const DASHBOARD_FILE = path.join(__dirname, 'dashboard.html');
const DASHBOARD_URL = pathToFileURL(DASHBOARD_FILE).href;

app.setName('Mudra');
app.setDesktopName(DESKTOP_ID);

let child = null;
let dashboardWindow = null;
let shuttingDown = false;
let currentSettings = defaults();

function pythonArgs() {
  const raw = process.env.MUDRA_PYTHON_ARGS_JSON || '[]';
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (error) {
    throw new Error(`Invalid MUDRA_PYTHON_ARGS_JSON: ${error.message}`);
  }
  if (!Array.isArray(parsed) || !parsed.every((value) => typeof value === 'string')) {
    throw new Error('MUDRA_PYTHON_ARGS_JSON must be a JSON array of strings');
  }
  return parsed;
}

function settingsPath() {
  return path.join(app.getPath('userData'), 'dashboard-settings.json');
}

function loadPersistedSettings() {
  const file = settingsPath();
  try {
    const raw = fs.readFileSync(file, 'utf8');
    return applyUpdates(defaults(), JSON.parse(raw));
  } catch (error) {
    if (error && error.code !== 'ENOENT') {
      console.warn(`Ignoring invalid saved dashboard settings: ${error.message}`);
    }
    return defaults();
  }
}

function persistSettings() {
  const file = settingsPath();
  const temp = `${file}.tmp`;
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(temp, JSON.stringify(currentSettings, null, 2) + '\n', {
    encoding: 'utf8',
    mode: 0o600
  });
  fs.renameSync(temp, file);
}

function sendControl(command) {
  if (!child || !child.stdin || !child.stdin.writable) return false;
  const payload = typeof command === 'string' ? command : JSON.stringify(command);
  child.stdin.write(`${payload}\n`);
  return true;
}

function registerShortcut(accelerator, command) {
  const submitted = globalShortcut.register(accelerator, () => {
    sendControl(command);
  });
  if (!submitted) {
    console.error(`Failed to submit global shortcut: ${accelerator}`);
  }
  return submitted;
}

function assertDashboardSender(event) {
  const sender = event.senderFrame && event.senderFrame.url;
  if (sender !== DASHBOARD_URL) {
    throw new Error('Dashboard IPC rejected for an unexpected sender.');
  }
}

function dashboardState() {
  return {
    settings: SETTINGS,
    values: currentSettings,
    connected: Boolean(child && child.stdin && child.stdin.writable),
    persisted: true
  };
}

function installDashboardIpc() {
  ipcMain.handle('dashboard:get-state', (event) => {
    assertDashboardSender(event);
    return dashboardState();
  });

  ipcMain.handle('dashboard:set-setting', (event, key, value) => {
    assertDashboardSender(event);
    if (typeof key !== 'string' || !(key in SETTINGS)) {
      throw new Error('Diese Einstellung ist nicht freigegeben.');
    }
    currentSettings = applyUpdate(currentSettings, key, value);
    persistSettings();
    sendControl({ type: 'setting', key, value: currentSettings[key] });
    return { value: currentSettings[key], connected: dashboardState().connected };
  });

  ipcMain.handle('dashboard:reset-settings', (event) => {
    assertDashboardSender(event);
    currentSettings = defaults();
    persistSettings();
    sendControl({ type: 'settings', values: currentSettings });
    return dashboardState();
  });
}

function createDashboard() {
  dashboardWindow = new BrowserWindow({
    title: 'Mudra – Einstellungen',
    width: 1120,
    height: 900,
    minWidth: 760,
    minHeight: 640,
    backgroundColor: '#ffffff',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true
    }
  });

  dashboardWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  dashboardWindow.webContents.on('will-navigate', (event, url) => {
    if (url !== DASHBOARD_URL) event.preventDefault();
  });
  dashboardWindow.on('closed', () => {
    dashboardWindow = null;
  });
  dashboardWindow.loadFile(DASHBOARD_FILE);
}

function requestShutdown() {
  if (shuttingDown) return;
  shuttingDown = true;
  sendControl('quit');

  const timer = setTimeout(() => {
    if (child && !child.killed) child.kill('SIGTERM');
    app.quit();
  }, 1500);
  timer.unref();
}

app.whenReady().then(() => {
  installDashboardIpc();

  const root = path.resolve(__dirname, '..');
  const args = pythonArgs();

  currentSettings = loadPersistedSettings();
  currentSettings = fromPythonArgs(currentSettings, args);

  child = spawn(
    'python3',
    [path.join(root, 'mudra.py'), '--control-stdin', ...args],
    {
      cwd: root,
      stdio: ['pipe', 'inherit', 'inherit'],
      env: { ...process.env, PYTHONUNBUFFERED: '1' },
      shell: false
    }
  );

  child.on('error', (error) => {
    console.error(`Failed to start mudra.py: ${error.message}`);
    process.exitCode = 1;
    app.quit();
  });

  child.on('exit', (code, signal) => {
    child = null;
    if (code && code !== 0) {
      console.error(`mudra.py exited with code ${code}${signal ? ` (signal ${signal})` : ''}`);
      process.exitCode = code;
    }
    app.quit();
  });

  // The pipe can buffer this until Python creates its ControlChannel.
  sendControl({ type: 'settings', values: currentSettings });

  createDashboard();

  registerShortcut(PAUSE_SHORTCUT, 'pause');
  registerShortcut(QUIT_SHORTCUT, 'quit');

  if (process.env.XDG_SESSION_TYPE === 'wayland') {
    console.log(
      'Global shortcuts requested through the XDG GlobalShortcuts portal. ' +
      'GNOME may ask for consent on first use.'
    );
  }

  if (typeof globalShortcut.on === 'function') {
    globalShortcut.on('registration-resolved', (accelerator, bound) => {
      console.log(`Global shortcut ${accelerator}: ${bound ? 'bound' : 'not bound'}`);
    });
  }
}).catch((error) => {
  console.error(error);
  process.exitCode = 1;
  app.quit();
});

app.on('window-all-closed', () => {
  // Closing the dashboard must not silently stop hand control.
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
  if (child && !child.killed) {
    child.kill('SIGTERM');
  }
});

process.on('SIGINT', requestShutdown);
process.on('SIGTERM', requestShutdown);
