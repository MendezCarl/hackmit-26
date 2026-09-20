const assert = require('node:assert/strict');
const test = require('node:test');
test('resolveRoute accepts every supported page hash', async () => {
  const { resolveRoute } = await import('../../dist/renderer/app/router.mjs');
  assert.equal(resolveRoute('#/student-summary'), 'student-summary');
  assert.equal(resolveRoute('#educator-dashboard'), 'educator-dashboard');
  assert.equal(resolveRoute('#/lecture-library?course=bio-101'), 'lecture-library');
});

test('resolveRoute falls back for missing or unsupported pages', async () => {
  const { resolveRoute } = await import('../../dist/renderer/app/router.mjs');
  assert.equal(resolveRoute(''), 'student-dashboard');
  assert.equal(resolveRoute('#/not-a-page'), 'student-dashboard');
});

test('buildRouteHash returns the canonical navigation form', async () => {
  const { buildRouteHash } = await import('../../dist/renderer/app/router.mjs');
  assert.equal(buildRouteHash('account'), '#/account');
  assert.equal(buildRouteHash('educator-summary'), '#/educator-summary');
});
