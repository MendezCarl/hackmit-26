const assert = require('node:assert/strict');
const { readFile } = require('node:fs/promises');
const { join } = require('node:path');
const test = require('node:test');
const routes = [
  'student-dashboard',
  'student-summary',
  'lecture-library',
  'educator-dashboard',
  'educator-summary',
  'account',
  'login',
];

test('every wireframe route renders a complete Bloom page', async () => {
  const { renderPage } = await import('../../dist/renderer/app/render_page.mjs');
  for (const route of routes) {
    const page = renderPage(route);
    assert.match(page, /class="app-frame"/);
    assert.match(page, /Bloom/);
    assert.ok(page.length > 500);
  }
});

test('pages use the repository Bloom asset instead of a drawn placeholder', async () => {
  const { renderPage } = await import('../../dist/renderer/app/render_page.mjs');
  assert.match(renderPage('student-dashboard'), /\.\/assets\/bloom-icon\.svg/);
  assert.match(renderPage('login'), /\.\/assets\/bloom-icon\.svg/);
});

test('educator pages use recovery language instead of attention claims', async () => {
  const { renderPage } = await import('../../dist/renderer/app/render_page.mjs');
  const educatorPages = [
    renderPage('educator-dashboard'),
    renderPage('educator-summary'),
  ].join(' ');

  assert.doesNotMatch(educatorPages, /attention ratio/i);
  assert.doesNotMatch(educatorPages, /students? lost focus/i);
  assert.match(educatorPages, /Anonymous aggregate/);
  assert.match(educatorPages, /Evidence coverage/);
});

test('the Electron renderer loads browser-native modules', async () => {
  const builtIndex = await readFile(
    join(__dirname, '..', '..', 'dist', 'index.html'),
    'utf8',
  );

  assert.match(
    builtIndex,
    /<script type="module" src="\.\/renderer\/index\.mjs"><\/script>/,
  );
  assert.doesNotMatch(builtIndex, /src="\.\/renderer\.js"/);
});
