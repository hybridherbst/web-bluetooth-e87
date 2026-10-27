import assert from 'node:assert/strict';
import test from 'node:test';
import { canvasToBadgeJpeg } from '../web/src/lib/image-encoding.ts';

test('desktop frames bypass the WebKit JPEG encoder and preserve raw RGBA pixels', async () => {
  const pixels = new Uint8ClampedArray([255, 80, 0, 128]);
  const expected = new Uint8Array([0xff, 0xd8, 0xff, 0xd9]);
  const previous = globalThis.window;
  let called = false;
  globalThis.window = { e87Desktop: { encodeJpeg: async (rgba, w, h, quality) => {
    called = true;
    assert.deepEqual(rgba, pixels);
    assert.deepEqual([w, h, quality], [1, 1, 0.92]);
    return expected;
  } } };
  try {
    const canvas = {
      width: 1, height: 1,
      getContext: () => ({ getImageData: (...args) => {
        assert.deepEqual(args, [0, 0, 1, 1]);
        return { data: pixels };
      } }),
      convertToBlob: () => { throw new Error('Must not use the system JPEG encoder'); },
    };
    assert.equal(await canvasToBadgeJpeg(canvas, 0.92), expected);
    assert.ok(called);
  } finally { globalThis.window = previous; }
});

test('a native encoding error cannot silently fall back to incompatible WebKit output', async () => {
  const previous = globalThis.window;
  globalThis.window = { e87Desktop: { encodeJpeg: async () => { throw new Error('Encoder unavailable'); } } };
  try {
    await assert.rejects(canvasToBadgeJpeg({
      width: 1, height: 1,
      getContext: () => ({ getImageData: () => ({ data: new Uint8ClampedArray(4) }) }),
      convertToBlob: () => { throw new Error('Unsafe fallback'); },
    }), /Encoder unavailable/);
  } finally { globalThis.window = previous; }
});

test('the standalone browser retains its existing canvas JPEG path', async () => {
  const previous = globalThis.window;
  globalThis.window = {};
  try {
    const canvas = { convertToBlob: async options => {
      assert.deepEqual(options, { type: 'image/jpeg', quality: 0.88 });
      return new Blob([new Uint8Array([1, 2, 3])]);
    } };
    assert.deepEqual(await canvasToBadgeJpeg(canvas), new Uint8Array([1, 2, 3]));
  } finally { globalThis.window = previous; }
});
