import { test } from 'node:test';
import assert from 'node:assert/strict';
import { normalizeMAC, systemMAC } from '../web/src/studio/lib/device-identity.ts';
import { scrollLayout } from '../web/src/studio/text-layout.ts';
test('macOS synthetic MAC-shaped identifiers never become hardware MACs', () => {
  assert.equal(systemMAC('12:34:56:78:9A:BC', 'darwin'), '');
  assert.equal(systemMAC('AA:BB:CC:DD:EE:FF', 'linux'), 'AA:BB:CC:DD:EE:FF');
  assert.equal(systemMAC('00000000-1111-2222-3333-444444444444', 'darwin'), '');
});
test('QR links and hand-entered addresses are parsed locally and validated', () => {
  assert.equal(normalizeMAC('https://example.com/badge?mac=AA%3ABB%3ACC%3ADD%3AEE%3AFF'), 'AA:BB:CC:DD:EE:FF');
  assert.equal(normalizeMAC('aa-bb-cc-dd-ee-ff'), 'AA:BB:CC:DD:EE:FF');
  assert.equal(normalizeMAC('AA:BB:CC:DD:EE:GG'), '');
  assert.equal(normalizeMAC('https://example.com/?notmac=AA:BB:CC:DD:EE:FF'), '');
});
test('scroll duration honors speed and rejects excessively long or invalid loops', () => {
  const layout = scrollLayout(620, 170);
  assert.equal(layout.count, 90);
  assert.equal(layout.duration, 6);
  assert.ok(scrollLayout(620, 260).count < layout.count);
  assert.throws(() => scrollLayout(3000, 100), /слишком длинный/);
  assert.throws(() => scrollLayout(100, 0), /Некорректные/);
});
