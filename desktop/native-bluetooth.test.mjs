import { test } from 'node:test';
import assert from 'node:assert/strict';
import { NativeBluetooth } from '../web/src/studio/native-bluetooth.ts';

const service = '0000ae00-0000-1000-8000-00805f9b34fb';
const char = '0000ae01-0000-1000-8000-00805f9b34fb';
function fixture() {
  const calls = [];
  const adapter = new NativeBluetooth(async (command, args) => {
    calls.push({ command, args });
    if (command === 'ble_select') return args.deviceId ? { deviceId: args.deviceId, deviceName: 'E87' } : null;
    if (command === 'ble_connect') return [{ uuid: service, characteristics: [{ uuid: char, properties: { writeWithoutResponse: true, notify: true } }] }];
    if (command === 'ble_read') return [42];
  });
  return { adapter, calls };
}
async function connected(adapter) {
  const pending = adapter.requestDevice();
  assert.equal(await adapter.select(1, 'badge'), true);
  const device = await pending;
  await device.gatt.connect();
  const c = await (await device.gatt.getPrimaryService(0xae00)).getCharacteristic(0xae01);
  return { device, c };
}
test('stale search results and selections cannot complete a newer request', async () => {
  const { adapter } = fixture();
  const scans = []; adapter.onDevices(scan => scans.push(scan));
  const first = adapter.requestDevice();
  const rejected = assert.rejects(first, { name: 'NotFoundError' });
  await adapter.select(1, ''); await rejected;
  const second = adapter.requestDevice();
  adapter.receiveScan({ requestId: 1, devices: [{ deviceId: 'old' }] });
  assert.equal(scans.at(-1).requestId, 2);
  assert.equal(await adapter.select(1, 'old'), false);
  await adapter.select(2, 'new'); assert.equal((await second).id, 'new');
});
test('notification events carry the characteristic target expected by the unchanged E87 protocol', async () => {
  const { adapter } = fixture(); const { c } = await connected(adapter);
  const received = [];
  c.addEventListener('characteristicvaluechanged', event => received.push(Array.from(new Uint8Array(event.target.value.buffer))));
  await c.startNotifications();
  adapter.receiveNotification({ sessionId: 9, uuid: char, value: [99] });
  adapter.receiveNotification({ sessionId: 1, uuid: char, value: [0xfe, 0xdc, 0xba] });
  await c.stopNotifications();
  adapter.receiveNotification({ sessionId: 1, uuid: char, value: [99] });
  assert.deepEqual(received, [[0xfe, 0xdc, 0xba]]);
});
test('writes preserve typed array/DataView boundaries and select the correct GATT write type', async () => {
  const { adapter, calls } = fixture(); const { c } = await connected(adapter);
  const buffer = Uint8Array.from([99, 1, 2, 88]).buffer;
  await c.writeValueWithoutResponse(new DataView(buffer, 1, 2));
  await c.writeValue(new Uint8Array(buffer, 2, 1));
  const writes = calls.filter(c => c.command === 'ble_write');
  assert.deepEqual(writes.map(c => [c.args.bytes, c.args.withoutResponse]), [[[1, 2], true], [[2], false]]);
});
test('disconnect emits once, rejects old characteristic writes and ignores late notifications', async () => {
  const { adapter } = fixture(); const { device, c } = await connected(adapter);
  let disconnects = 0, notifications = 0;
  device.addEventListener('gattserverdisconnected', () => disconnects++);
  c.addEventListener('characteristicvaluechanged', () => notifications++);
  await c.startNotifications();
  adapter.receiveDisconnect(1); adapter.receiveDisconnect(1);
  adapter.receiveNotification({ sessionId: 1, uuid: char, value: [99] });
  assert.equal(device.gatt.connected, false); assert.equal(disconnects, 1); assert.equal(notifications, 0);
  await assert.rejects(c.writeValue(new Uint8Array([1])), /отключён/);
});
test('scan initialization failure closes the chooser and reaches the caller', async () => {
  const adapter = new NativeBluetooth(async () => { throw 'Bluetooth permission denied'; });
  const scans = []; adapter.onDevices(scan => scans.push(scan));
  await assert.rejects(adapter.requestDevice(), /permission denied/); assert.equal(scans.at(-1), null);
});
