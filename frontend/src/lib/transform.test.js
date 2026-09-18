import assert from 'node:assert/strict';
import { test } from 'node:test';
import { localDateIso } from './transform.js';

test('localDateIso uses local calendar components, not UTC ISO slice', () => {
  const localMorning = new Date(2026, 8, 19, 4, 0, 0);
  assert.equal(localDateIso(localMorning), '2026-09-19');
});

test('Perth UTC+8: 20:00 UTC is still the previous UTC date but local next morning', (t) => {
  const instant = new Date('2026-09-18T20:00:00.000Z');
  assert.equal(instant.toISOString().slice(0, 10), '2026-09-18');
  // Australia/Perth is UTC+8 with no DST (offset minutes = -480).
  if (instant.getTimezoneOffset() !== -480) {
    t.skip('Requires TZ=Australia/Perth (UTC+8, no DST)');
    return;
  }
  assert.equal(localDateIso(instant), '2026-09-19');
});
