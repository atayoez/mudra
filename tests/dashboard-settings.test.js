'use strict';

const assert = require('node:assert/strict');
const {
  SETTINGS,
  defaults,
  applyUpdate,
  applyUpdates,
  fromPythonArgs,
  validateState
} = require('../electron/settings');

const base = defaults();
assert.equal(Object.keys(base).length, Object.keys(SETTINGS).length);
assert.deepEqual(validateState({ ...base }), base);

assert.equal(applyUpdate(base, 'scroll_speed', 120).scroll_speed, 120);
assert.throws(() => applyUpdate(base, 'unknown', 1), /Unbekannte Einstellung/);
assert.throws(() => applyUpdate(base, 'conf', 1.0), /zwischen/);
assert.throws(() => applyUpdate(base, 'smart_pinky', 1), /Ein oder Aus/);
assert.throws(
  () => applyUpdates(base, { tap_lift: 0.08, tap_return: 0.09 }),
  /kleiner/
);
assert.throws(
  () => applyUpdates(base, { thumb_lift: 0.08, thumb_return: 0.09 }),
  /kleiner/
);

const cli = fromPythonArgs(base, [
  '--scroll-speed', '140',
  '--tap-lift=0.18',
  '--no-smart-pinky',
  '--invert-scroll'
]);
assert.equal(cli.scroll_speed, 140);
assert.equal(cli.tap_lift, 0.18);
assert.equal(cli.smart_pinky, false);
assert.equal(cli.invert_scroll, true);

console.log('Dashboard settings tests passed.');
