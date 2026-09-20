---
name: bloom-local-electron-testing
description: Exercise professor and student lecture flows in separate Electron windows against the local FastAPI backend.
---

# Local desktop integration testing

## Devin Secrets Needed
None for synthetic local accounts. Do not use production student data.

## Start the real services
- From `backend/`, run `APP_ENV=test .venv/bin/uvicorn app.main:app --port 8000`.
- From `frontend/`, run `npm run build`.
- Launch each role with `BLOOM_BACKEND_URL=http://127.0.0.1:8000 npx electron . --user-data-dir=/tmp/bloom-<role>`. The default backend is hosted, so explicitly override it.
- Separate Electron processes isolate authentication. Maximize each via `wmctrl -r :ACTIVE: -b add,maximized_vert,maximized_horz` on Linux, and switch with Alt+Tab.
- Register synthetic student/professor accounts through UI or the documented auth/register endpoint. Never extract browser session cookies for API tests.
- Backend storage may be ephemeral; prepare courses again after a restart.

## UI navigation
- Professor Home → Courses + → course title/code → Create course.
- Open course in sidebar → enter lecture title → Create lecture.
- Open lecture in sidebar → Start session. The active lecture panel exposes its join code and End session.
- Student Home contains Have a code?, Your courses, and active lecture details. Scroll down to inspect participant count.
- Enrollment removal is the × icon with an accessible Leave label.
- Course auto-join checkbox is labeled Join lectures automatically.

## Meaningful lifecycle checks
- Discovery polling is 20 seconds; keep the student dashboard open and untouched for 22–25 seconds after a professor starts a lecture.
- Verify both idle-dashboard auto-join and consecutive-lecture behavior after a professor ends the previous session. These exercise different paths: the latter must refresh the old session's backend status.
- Include the complementary guard: start another available lecture while the current lecture remains live, verify the app keeps the current lecture, then end it and verify automatic switching.
- Reload may return to login. Reauthentication is a useful clean-state diagnostic, not proof that uninterrupted lecture switching works.
- Keep camera and transcript-provider consent disabled unless explicitly testing those integrations.
- New panels may be below the fold; inspect visible screenshots rather than inferring appearance from markup.
