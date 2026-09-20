const assert = require('node:assert/strict');
const test = require('node:test');

const withFakeFetch = async (run) => {
  const requests = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    requests.push({ url: String(url), method: init.method, body: init.body });
    if (init.method === 'DELETE') return new Response(null, { status: 204 });
    return new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } });
  };
  try {
    await run(requests);
  } finally {
    globalThis.fetch = originalFetch;
  }
};

test('BackendClient maps enrollment operations to the /api/v1 enrollment routes', async () => {
  const { BackendClient } = await import('../../dist/main/backend_client.js');
  await withFakeFetch(async (requests) => {
    const client = new BackendClient('http://127.0.0.1:8000');
    await client.listEnrollments();
    await client.enrollInCourse({ course_code: 'cs101' });
    await client.updateEnrollment('enrollment 1', { is_auto_join_enabled: true });
    await client.leaveCourse('enrollment 1');
    assert.deepEqual(
      requests.map(({ method, url }) => [method, url]),
      [
        ['GET', 'http://127.0.0.1:8000/api/v1/enrollments'],
        ['POST', 'http://127.0.0.1:8000/api/v1/enrollments'],
        ['PATCH', 'http://127.0.0.1:8000/api/v1/enrollments/enrollment%201'],
        ['DELETE', 'http://127.0.0.1:8000/api/v1/enrollments/enrollment%201'],
      ],
    );
    assert.equal(requests[1].body, JSON.stringify({ course_code: 'cs101' }));
    assert.equal(requests[2].body, JSON.stringify({ is_auto_join_enabled: true }));
  });
});

test('BackendClient only sends zoom_meeting_id to /sessions/available when known', async () => {
  const { BackendClient } = await import('../../dist/main/backend_client.js');
  await withFakeFetch(async (requests) => {
    const client = new BackendClient('http://127.0.0.1:8000');
    await client.listAvailableSessions();
    await client.listAvailableSessions(null);
    await client.listAvailableSessions('987654321');
    assert.deepEqual(
      requests.map(({ url }) => url),
      [
        'http://127.0.0.1:8000/api/v1/sessions/available',
        'http://127.0.0.1:8000/api/v1/sessions/available',
        'http://127.0.0.1:8000/api/v1/sessions/available?zoom_meeting_id=987654321',
      ],
    );
  });
});
