import assert from 'node:assert/strict';
import test from 'node:test';
import { frameRect, previewDimensions } from '../web/src/lib/frame-layout.ts';

test('photo caches preserve portrait, landscape and panorama bounds without a square crop', () => {
  assert.deepEqual(previewDimensions(4000, 2000, 4096), { width: 4000, height: 2000 });
  assert.deepEqual(previewDimensions(3000, 6000, 4096), { width: 2048, height: 4096 });
  assert.deepEqual(previewDimensions(10000, 1000, 1024), { width: 1024, height: 102 });
});

test('the full left and right edges of a wide photo remain reachable after import', () => {
  const firstEdge = frameRect(4000, 1000, 368, 368, { scale: 1, panX: 3, panY: 0 });
  const lastEdge = frameRect(4000, 1000, 368, 368, { scale: 1, panX: -3, panY: 0 });
  assert.equal(firstEdge.width / firstEdge.height, 4);
  assert.equal(firstEdge.x, 0);
  assert.equal(lastEdge.x + lastEdge.width, 368);
});

test('the full top and bottom edges of a portrait remain reachable after import', () => {
  const firstEdge = frameRect(1000, 4000, 368, 368, { scale: 1, panX: 0, panY: 3 });
  const lastEdge = frameRect(1000, 4000, 368, 368, { scale: 1, panX: 0, panY: -3 });
  assert.equal(firstEdge.height / firstEdge.width, 4);
  assert.equal(firstEdge.y, 0);
  assert.equal(lastEdge.y + lastEdge.height, 368);
});

test('preview and JPEG export use identical framing after zoom and pan', () => {
  const transform = { scale: 2.3, panX: -2.1, panY: 0.7 };
  const preview = frameRect(4000, 3000, 220, 220, transform);
  const output = frameRect(4000, 3000, 360, 360, transform);
  for (const key of ['x', 'y', 'width', 'height']) {
    assert.ok(Math.abs(preview[key] / 220 - output[key] / 360) < 1e-12);
  }
});
