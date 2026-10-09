'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('mudraDashboard', Object.freeze({
  getState: () => ipcRenderer.invoke('dashboard:get-state'),
  setSetting: (key, value) => ipcRenderer.invoke(
    'dashboard:set-setting', key, value
  ),
  resetSettings: () => ipcRenderer.invoke('dashboard:reset-settings')
}));
