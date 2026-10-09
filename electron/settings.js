'use strict';

const SETTINGS = Object.freeze({
  tap_lift: {
    type: 'number',
    group: 'Klicks mit Zeige-, Ring- und kleinem Finger',
    label: 'Finger anheben – Auslöseschwelle',
    description: 'Wie weit sich ein Finger von seiner gelernten Ruhelage entfernen muss, bevor ein Tap erkannt werden kann.',
    lower: 'Empfindlicher. Kleine Bewegungen reichen, aber Fehlklicks werden wahrscheinlicher.',
    higher: 'Unempfindlicher. Der Finger muss deutlicher angehoben werden, dafür gibt es weniger Fehlklicks.',
    default: 0.14, min: 0.05, max: 0.30, step: 0.005, precision: 3
  },
  tap_return: {
    type: 'number',
    group: 'Klicks mit Zeige-, Ring- und kleinem Finger',
    label: 'Finger zurücklegen – Klickpunkt',
    description: 'Wie nah der Finger wieder an seine Ruhelage kommen muss, damit der Tap als Klick ausgelöst wird.',
    lower: 'Der Finger muss fast vollständig zurück auf den Tisch.',
    higher: 'Der Klick wird früher beim Absenken ausgelöst. Dieser Wert muss kleiner als die Auslöseschwelle bleiben.',
    default: 0.055, min: 0.01, max: 0.12, step: 0.005, precision: 3
  },
  tap_cooldown: {
    type: 'number',
    group: 'Klicks mit Zeige-, Ring- und kleinem Finger',
    label: 'Mindestpause zwischen Klicks',
    description: 'Mindestzeit in Sekunden, bevor derselbe Finger erneut einen Klick auslösen darf.',
    lower: 'Schnellere Doppelklicks sind möglich, aber Zittern kann eher mehrere Klicks erzeugen.',
    higher: 'Mehr Schutz vor Mehrfachklicks, dafür langsamere Wiederholungen.',
    default: 0.22, min: 0.05, max: 0.80, step: 0.01, precision: 2, unit: 's'
  },
  thumb_lift: {
    type: 'number',
    group: 'Drag & Drop mit dem Daumen',
    label: 'Daumen anheben – Drag starten',
    description: 'Wie weit der Daumen von seiner Ruhelage weg muss, bevor die linke Maustaste gehalten wird.',
    lower: 'Drag startet bei kleinerer Daumenbewegung.',
    higher: 'Drag startet erst bei einem deutlicher angehobenen Daumen.',
    default: 0.16, min: 0.05, max: 0.35, step: 0.005, precision: 3
  },
  thumb_return: {
    type: 'number',
    group: 'Drag & Drop mit dem Daumen',
    label: 'Daumen zurücklegen – Objekt loslassen',
    description: 'Wie nah der Daumen wieder an seine Ruhelage kommen muss, damit Drag beendet und das Objekt abgelegt wird.',
    lower: 'Der Daumen muss näher an den Tisch zurück.',
    higher: 'Das Objekt wird früher losgelassen. Dieser Wert muss kleiner als die Drag-Auslöseschwelle bleiben.',
    default: 0.065, min: 0.01, max: 0.15, step: 0.005, precision: 3
  },
  four_finger_scroll: {
    type: 'boolean',
    group: 'Scrollen mit vier Fingern',
    label: 'Vier-Finger-Scrollen aktivieren',
    description: 'Zeige-, Mittel-, Ring- und kleiner Finger bewegen sich gemeinsam auf dem Tisch nach oben oder unten.',
    onText: 'Aktiv – die Vier-Finger-Geste kann scrollen.',
    offText: 'Aus – vier Finger bewegen weiterhin nur den normalen Zeiger.',
    default: true
  },
  scroll_rest: {
    type: 'number',
    group: 'Scrollen mit vier Fingern',
    label: 'Wie streng „auf dem Tisch“ erkannt wird',
    description: 'Maximal erlaubte Abweichung von der gelernten Ruhelage für alle vier Scroll-Finger.',
    lower: 'Strenger. Scrollen startet nur, wenn alle Finger sehr nah an ihrer Ruhelage sind.',
    higher: 'Toleranter bei unebener Handhaltung, kann aber leichter versehentlich scrollen.',
    default: 0.085, min: 0.02, max: 0.20, step: 0.005, precision: 3
  },
  scroll_start: {
    type: 'number',
    group: 'Scrollen mit vier Fingern',
    label: 'Bewegung zum Starten des Scrollens',
    description: 'Wie viel gemeinsame vertikale Bewegung nötig ist, bevor Mudra in den Scrollmodus wechselt.',
    lower: 'Scrollen reagiert schneller auf kleine Bewegungen.',
    higher: 'Es braucht eine deutlichere Bewegung und versehentliches Scrollen wird unwahrscheinlicher.',
    default: 0.006, min: 0.001, max: 0.03, step: 0.001, precision: 3
  },
  scroll_speed: {
    type: 'number',
    group: 'Scrollen mit vier Fingern',
    label: 'Scroll-Geschwindigkeit',
    description: 'Wie viele Mausrad-Schritte aus der Bewegung der vier Finger erzeugt werden.',
    lower: 'Langsamer und feiner scrollen.',
    higher: 'Schneller durch lange Seiten und Listen scrollen.',
    default: 95.0, min: 10.0, max: 300.0, step: 5.0, precision: 0
  },
  scroll_release: {
    type: 'number',
    group: 'Scrollen mit vier Fingern',
    label: 'Scrollmodus nach Stillstand beenden',
    description: 'Wie lange Mudra nach dem letzten Scrollimpuls wartet, bevor wieder normale Cursor- und Klickgesten gelten.',
    lower: 'Schneller zurück zur normalen Bedienung.',
    higher: 'Scrollmodus bleibt bei kurzen Pausen stabiler aktiv.',
    default: 0.16, min: 0.05, max: 0.60, step: 0.01, precision: 2, unit: 's'
  },
  invert_scroll: {
    type: 'boolean',
    group: 'Scrollen mit vier Fingern',
    label: 'Scrollrichtung umkehren',
    description: 'Vertauscht die Richtung der Vier-Finger-Bewegung.',
    onText: 'Umgekehrt – Finger nach oben scrollen in die andere Richtung.',
    offText: 'Normal – Finger nach oben erzeugen Mausrad nach oben.',
    default: false
  },
  median: {
    type: 'number',
    integer: true,
    group: 'Zeiger und Handerkennung',
    label: 'Ausreißer glätten',
    description: 'Anzahl der letzten Cursorpositionen, aus denen ein Median gebildet wird.',
    lower: 'Direkter und schneller, aber einzelne Messfehler sind stärker sichtbar.',
    higher: 'Ruhigerer Zeiger, dafür etwas mehr Verzögerung.',
    default: 3, min: 1, max: 9, step: 1, precision: 0
  },
  mincutoff: {
    type: 'number',
    group: 'Zeiger und Handerkennung',
    label: 'Grundglättung des Zeigers',
    description: 'One-Euro-Filter: bestimmt, wie stark langsame Bewegungen und Stillstand geglättet werden.',
    lower: 'Ruhigerer Zeiger im Stillstand, aber etwas mehr Verzögerung.',
    higher: 'Direkterer Zeiger, aber sichtbarer empfindlich auf Zittern.',
    default: 1.0, min: 0.10, max: 5.0, step: 0.10, precision: 2
  },
  beta: {
    type: 'number',
    group: 'Zeiger und Handerkennung',
    label: 'Beschleunigung bei schnellen Bewegungen',
    description: 'One-Euro-Filter: wie stark schnelle Handbewegungen weniger geglättet werden.',
    lower: 'Gleichmäßiger, aber schnelle Bewegungen können hinterherhinken.',
    higher: 'Schnelle Bewegungen reagieren direkter, können aber unruhiger wirken.',
    default: 0.05, min: 0.0, max: 0.30, step: 0.01, precision: 2
  },
  conf: {
    type: 'number',
    group: 'Zeiger und Handerkennung',
    label: 'Mindest-Sicherheit der Handerkennung',
    description: 'Wie sicher das Handmodell sein muss, bevor Mudra die erkannten Punkte verwendet.',
    lower: 'Hand bleibt bei schwierigen Winkeln eher aktiv, aber unsichere Messungen werden häufiger akzeptiert.',
    higher: 'Nur sichere Erkennungen werden genutzt, dafür kann die Hand früher kurz verloren gehen.',
    default: 0.80, min: 0.40, max: 0.95, step: 0.01, precision: 2
  },
  smart_pinky: {
    type: 'boolean',
    group: 'Funktionen',
    label: 'Intelligentes Copy/Paste mit kleinem Finger',
    description: 'Bei Auswahl wird kopiert; in einem editierbaren Feld ohne Auswahl wird eingefügt. Unklarer Kontext löst nichts aus.',
    onText: 'Aktiv – der kleine Finger nutzt den barrierearmen AT-SPI-Kontext.',
    offText: 'Aus – der kleine Finger löst kein Copy/Paste aus.',
    default: true
  }
});

function defaults() {
  return Object.fromEntries(
    Object.entries(SETTINGS).map(([key, spec]) => [key, spec.default])
  );
}

function normalizeValue(key, value) {
  const spec = SETTINGS[key];
  if (!spec) throw new Error(`Unbekannte Einstellung: ${key}`);

  if (spec.type === 'boolean') {
    if (typeof value !== 'boolean') {
      throw new Error(`${spec.label} muss Ein oder Aus sein.`);
    }
    return value;
  }

  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`${spec.label} braucht eine gültige Zahl.`);
  }
  if (spec.integer && !Number.isInteger(value)) {
    throw new Error(`${spec.label} braucht eine ganze Zahl.`);
  }
  if (value < spec.min || value > spec.max) {
    throw new Error(
      `${spec.label} muss zwischen ${spec.min} und ${spec.max} liegen.`
    );
  }
  return value;
}

function validateState(state) {
  for (const key of Object.keys(SETTINGS)) {
    if (!(key in state)) throw new Error(`Einstellung fehlt: ${key}`);
    normalizeValue(key, state[key]);
  }
  if (state.tap_return >= state.tap_lift) {
    throw new Error(
      '„Finger zurücklegen – Klickpunkt“ muss kleiner als „Finger anheben – Auslöseschwelle“ sein.'
    );
  }
  if (state.thumb_return >= state.thumb_lift) {
    throw new Error(
      '„Daumen zurücklegen – Objekt loslassen“ muss kleiner als „Daumen anheben – Drag starten“ sein.'
    );
  }
  return state;
}

function applyUpdates(current, updates) {
  if (!updates || typeof updates !== 'object' || Array.isArray(updates)) {
    throw new Error('Ungültige Einstellungsdaten.');
  }
  const next = { ...current };
  for (const [key, value] of Object.entries(updates)) {
    next[key] = normalizeValue(key, value);
  }
  validateState(next);
  return next;
}

function applyUpdate(current, key, value) {
  return applyUpdates(current, { [key]: value });
}

const VALUE_FLAGS = Object.freeze({
  '--tap-lift': 'tap_lift',
  '--tap-return': 'tap_return',
  '--tap-cooldown': 'tap_cooldown',
  '--thumb-lift': 'thumb_lift',
  '--thumb-return': 'thumb_return',
  '--scroll-rest': 'scroll_rest',
  '--scroll-start': 'scroll_start',
  '--scroll-speed': 'scroll_speed',
  '--scroll-release': 'scroll_release',
  '--median': 'median',
  '--mincutoff': 'mincutoff',
  '--beta': 'beta',
  '--conf': 'conf'
});

function fromPythonArgs(current, argv) {
  const updates = {};
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];

    if (token === '--four-finger-scroll') updates.four_finger_scroll = true;
    else if (token === '--no-four-finger-scroll') updates.four_finger_scroll = false;
    else if (token === '--smart-pinky') updates.smart_pinky = true;
    else if (token === '--no-smart-pinky') updates.smart_pinky = false;
    else if (token === '--invert-scroll') updates.invert_scroll = true;
    else {
      let flag = token;
      let raw = null;
      const equals = token.indexOf('=');
      if (equals > 0) {
        flag = token.slice(0, equals);
        raw = token.slice(equals + 1);
      }
      const key = VALUE_FLAGS[flag];
      if (!key) continue;
      if (raw === null) {
        i += 1;
        raw = argv[i];
      }
      if (raw === undefined) throw new Error(`Wert fehlt für ${flag}`);
      const value = Number(raw);
      updates[key] = SETTINGS[key].integer ? Number.parseInt(raw, 10) : value;
    }
  }
  return applyUpdates(current, updates);
}

module.exports = {
  SETTINGS,
  defaults,
  applyUpdate,
  applyUpdates,
  fromPythonArgs,
  validateState
};
