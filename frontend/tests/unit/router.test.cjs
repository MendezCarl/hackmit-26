const assert = require('node:assert/strict');
const test = require('node:test');
test('resolveRoute accepts every supported page hash', async () => {
  const { resolveRoute } = await import('../../dist/renderer/app/router.mjs');
  assert.equal(resolveRoute('#/student-summary'), 'student-summary');
  assert.equal(resolveRoute('#educator-dashboard'), 'educator-dashboard');
  assert.equal(resolveRoute('#/lecture-library?course=bio-101'), 'lecture-library');
  assert.equal(resolveRoute('#/home'), 'home');
  assert.equal(resolveRoute('#/course?course_id=course-1'), 'course');
  assert.equal(resolveRoute('#/lecture?lecture_id=lecture-1'), 'lecture');
});

test('resolveRoute falls back for missing or unsupported pages', async () => {
  const { resolveRoute } = await import('../../dist/renderer/app/router.mjs');
  assert.equal(resolveRoute(''), 'student-dashboard');
  assert.equal(resolveRoute('#/not-a-page'), 'student-dashboard');
});

test('buildRouteHash returns the canonical navigation form', async () => {
  const { buildRouteHash, resolveRouteParams } = await import('../../dist/renderer/app/router.mjs');
  assert.equal(buildRouteHash('account'), '#/account');
  assert.equal(buildRouteHash('educator-summary'), '#/educator-summary');
  assert.equal(
    buildRouteHash('course', { course_id: 'course one', title: 'Biology & labs' }),
    '#/course?course_id=course+one&title=Biology+%26+labs',
  );
  const params = resolveRouteParams('#/lecture?lecture_id=lecture-1&tab=timeline');
  assert.equal(params.get('lecture_id'), 'lecture-1');
  assert.equal(params.get('tab'), 'timeline');
});
