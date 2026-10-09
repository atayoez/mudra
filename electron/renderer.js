'use strict';

const api = window.mudraDashboard;
const container = document.getElementById('settings-container');
const status = document.getElementById('connection-status');
const resetButton = document.getElementById('reset-settings');

let state = null;
const controls = new Map();

function setStatus(message, kind = 'ok') {
  status.textContent = message;
  status.dataset.state = kind;
}

function formatNumber(value, spec) {
  const precision = Number.isInteger(spec.precision) ? spec.precision : 3;
  const formatted = Number(value).toLocaleString('de-DE', {
    minimumFractionDigits: precision,
    maximumFractionDigits: precision
  });
  return spec.unit ? `${formatted} ${spec.unit}` : formatted;
}

function updateCurrentValue(key, value) {
  const entry = controls.get(key);
  if (!entry) return;
  const { spec, output, range, number, checkbox, toggleState } = entry;

  if (spec.type === 'boolean') {
    checkbox.checked = Boolean(value);
    toggleState.textContent = value ? spec.onText : spec.offText;
    output.textContent = `Aktuell: ${value ? 'Ein' : 'Aus'}`;
  } else {
    range.value = String(value);
    number.value = String(value);
    output.textContent = `Aktuell: ${formatNumber(value, spec)}`;
  }
}

function clearError(key) {
  const entry = controls.get(key);
  if (!entry) return;
  entry.error.hidden = true;
  entry.error.textContent = '';
}

function showError(key, message) {
  const entry = controls.get(key);
  if (!entry) return;
  entry.error.textContent = message;
  entry.error.hidden = false;
}

async function commitSetting(key, value) {
  clearError(key);
  try {
    const result = await api.setSetting(key, value);
    state.values[key] = result.value;
    updateCurrentValue(key, result.value);
    setStatus(
      result.connected
        ? 'Verbunden – Änderung wurde live übernommen und gespeichert.'
        : 'Wert gespeichert. Die Python-Steuerung ist gerade nicht verbunden.',
      result.connected ? 'ok' : 'error'
    );
  } catch (error) {
    const message = error && error.message ? error.message : 'Änderung wurde abgelehnt.';
    showError(key, message);
    updateCurrentValue(key, state.values[key]);
    setStatus('Änderung wurde nicht übernommen. Bitte Erklärung am Regler prüfen.', 'error');
  }
}

function createNumberSetting(key, spec, value) {
  const card = document.createElement('article');
  card.className = 'setting-card';

  const title = document.createElement('h3');
  title.id = `title-${key}`;
  title.textContent = spec.label;
  card.appendChild(title);

  const description = document.createElement('p');
  description.id = `description-${key}`;
  description.className = 'setting-description';
  description.textContent = spec.description;
  card.appendChild(description);

  const output = document.createElement('output');
  output.className = 'current-value';
  output.setAttribute('for', `range-${key} number-${key}`);
  card.appendChild(output);

  const controlsWrap = document.createElement('div');
  controlsWrap.className = 'value-controls';

  const rangeWrap = document.createElement('div');
  rangeWrap.className = 'range-wrap';
  const rangeLabel = document.createElement('label');
  rangeLabel.className = 'control-label';
  rangeLabel.htmlFor = `range-${key}`;
  rangeLabel.textContent = 'Regler';
  const range = document.createElement('input');
  range.id = `range-${key}`;
  range.type = 'range';
  range.min = String(spec.min);
  range.max = String(spec.max);
  range.step = String(spec.step);
  range.value = String(value);
  range.setAttribute('aria-labelledby', title.id);
  range.setAttribute('aria-describedby', description.id);
  rangeWrap.append(rangeLabel, range);

  const numberWrap = document.createElement('div');
  numberWrap.className = 'number-wrap';
  const numberLabel = document.createElement('label');
  numberLabel.className = 'control-label';
  numberLabel.htmlFor = `number-${key}`;
  numberLabel.textContent = 'Genauer Wert';
  const number = document.createElement('input');
  number.id = `number-${key}`;
  number.type = 'number';
  number.min = String(spec.min);
  number.max = String(spec.max);
  number.step = String(spec.step);
  number.value = String(value);
  number.setAttribute('aria-labelledby', title.id);
  number.setAttribute('aria-describedby', description.id);
  numberWrap.append(numberLabel, number);

  controlsWrap.append(rangeWrap, numberWrap);
  card.appendChild(controlsWrap);

  const effects = document.createElement('div');
  effects.className = 'effect-grid';

  const lower = document.createElement('div');
  lower.className = 'effect';
  const lowerStrong = document.createElement('strong');
  lowerStrong.textContent = 'Kleinerer Wert';
  const lowerText = document.createElement('span');
  lowerText.textContent = spec.lower;
  lower.append(lowerStrong, lowerText);

  const higher = document.createElement('div');
  higher.className = 'effect';
  const higherStrong = document.createElement('strong');
  higherStrong.textContent = 'Größerer Wert';
  const higherText = document.createElement('span');
  higherText.textContent = spec.higher;
  higher.append(higherStrong, higherText);
  effects.append(lower, higher);
  card.appendChild(effects);

  const error = document.createElement('p');
  error.className = 'setting-error';
  error.setAttribute('role', 'alert');
  error.hidden = true;
  card.appendChild(error);

  controls.set(key, { spec, output, range, number, error });

  range.addEventListener('input', () => {
    number.value = range.value;
    output.textContent = `Aktuell gewählt: ${formatNumber(Number(range.value), spec)}`;
  });
  range.addEventListener('change', () => {
    commitSetting(key, Number(range.value));
  });
  number.addEventListener('change', () => {
    const next = spec.integer
      ? Number.parseInt(number.value, 10)
      : Number(number.value);
    commitSetting(key, next);
  });

  updateCurrentValue(key, value);
  return card;
}

function createBooleanSetting(key, spec, value) {
  const card = document.createElement('article');
  card.className = 'setting-card';

  const title = document.createElement('h3');
  title.id = `title-${key}`;
  title.textContent = spec.label;
  card.appendChild(title);

  const description = document.createElement('p');
  description.id = `description-${key}`;
  description.className = 'setting-description';
  description.textContent = spec.description;
  card.appendChild(description);

  const output = document.createElement('output');
  output.className = 'current-value';
  card.appendChild(output);

  const row = document.createElement('div');
  row.className = 'toggle-row';
  const checkbox = document.createElement('input');
  checkbox.id = `toggle-${key}`;
  checkbox.type = 'checkbox';
  checkbox.setAttribute('aria-labelledby', title.id);
  checkbox.setAttribute('aria-describedby', description.id);

  const textWrap = document.createElement('div');
  const label = document.createElement('label');
  label.className = 'control-label';
  label.htmlFor = checkbox.id;
  label.textContent = 'Ein / Aus';
  const toggleState = document.createElement('p');
  toggleState.className = 'toggle-state';
  textWrap.append(label, toggleState);
  row.append(checkbox, textWrap);
  card.appendChild(row);

  const error = document.createElement('p');
  error.className = 'setting-error';
  error.setAttribute('role', 'alert');
  error.hidden = true;
  card.appendChild(error);

  controls.set(key, { spec, output, checkbox, toggleState, error });

  checkbox.addEventListener('change', () => {
    commitSetting(key, checkbox.checked);
  });

  updateCurrentValue(key, value);
  return card;
}

function renderSettings() {
  container.replaceChildren();
  controls.clear();

  const groups = new Map();
  for (const [key, spec] of Object.entries(state.settings)) {
    if (!groups.has(spec.group)) groups.set(spec.group, []);
    groups.get(spec.group).push([key, spec]);
  }

  for (const [groupName, entries] of groups) {
    const section = document.createElement('section');
    section.className = 'settings-group';

    const heading = document.createElement('h2');
    heading.className = 'group-title';
    heading.textContent = groupName;
    section.appendChild(heading);

    for (const [key, spec] of entries) {
      const card = spec.type === 'boolean'
        ? createBooleanSetting(key, spec, state.values[key])
        : createNumberSetting(key, spec, state.values[key]);
      section.appendChild(card);
    }
    container.appendChild(section);
  }
}

function setupTextSize() {
  const saved = localStorage.getItem('mudra-text-size');
  const size = ['normal', 'large', 'xlarge'].includes(saved) ? saved : 'large';
  document.documentElement.dataset.textSize = size;

  for (const button of document.querySelectorAll('button[data-text-size]')) {
    button.setAttribute(
      'aria-pressed',
      button.dataset.textSize === size ? 'true' : 'false'
    );
    button.addEventListener('click', () => {
      const next = button.dataset.textSize;
      document.documentElement.dataset.textSize = next;
      localStorage.setItem('mudra-text-size', next);
      for (const other of document.querySelectorAll('button[data-text-size]')) {
        other.setAttribute(
          'aria-pressed',
          other.dataset.textSize === next ? 'true' : 'false'
        );
      }
    });
  }
}

resetButton.addEventListener('click', async () => {
  try {
    state = await api.resetSettings();
    renderSettings();
    setStatus('Standardwerte wurden wiederhergestellt, live übernommen und gespeichert.');
  } catch (error) {
    setStatus(
      error && error.message ? error.message : 'Standardwerte konnten nicht geladen werden.',
      'error'
    );
  }
});

(async () => {
  setupTextSize();
  try {
    state = await api.getState();
    renderSettings();
    setStatus(
      state.connected
        ? 'Verbunden – Änderungen werden live übernommen und gespeichert.'
        : 'Dashboard geöffnet, aber die Python-Steuerung ist nicht verbunden.',
      state.connected ? 'ok' : 'error'
    );
  } catch (error) {
    setStatus(
      error && error.message ? error.message : 'Dashboard konnte nicht initialisiert werden.',
      'error'
    );
  }
})();
