# Frontend Wireframe Implementation

**Status:** Implemented prototype

**Owner:** Frontend and Product teams

**Last updated:** 2026-09-20

## Purpose

Document the Bloom Electron screens implemented from the initial HackMIT wireframes. The prototype uses synthetic fixtures so the team can review navigation, terminology, information hierarchy, and responsive behavior before connecting live contracts.

The implementation uses the canonical Bloom asset at `frontend/src/assets/bloom-icon.svg`. Hand-drawn logo placeholders in the wireframes are not product assets.

## Page inventory

| Route | Audience | Purpose |
| --- | --- | --- |
| `#/student-dashboard` | Student | Upcoming-lecture consent prompt, recent lectures, and latest recovery summary |
| `#/student-summary` | Student | Interactive lecture timeline, AI recovery summary, and transcript excerpts |
| `#/lecture-library` | Student | Searchable and filterable catalog of lecture summaries |
| `#/educator-dashboard` | Educator | Evidence coverage, lecture continuity, recovery hotspots, delivery notes, concept checks, and review moments |
| `#/educator-summary` | Educator | Anonymous lecture report with an interactive timeline, aggregate evidence, and delivery-quality feedback |
| `#/account` | Student | Profile, local processing preferences, and local-data deletion controls |
| `#/login` | Shared | Login form and product introduction |

## Reusable components

- `AppShell` supplies the global navigation, course sidebar, responsive layout, and page heading.
- `TopNavigation` uses the repository Bloom logo and shows local-service status.
- `LoginNavigation` provides the reduced navigation used by the authentication page.
- `CourseSidebar` groups role-specific navigation and lecture history.
- `LectureTimeline` renders recovery hotspots and delivery notes as selectable intervals.
- `MetricCard` renders a headline educator metric with its denominator or definition.
- `MomentDetail` renders the selected timeline moment and supports in-place updates.
- `LectureCard` renders one lecture-library result.
- `ConsentDialog` renders the explicit pre-lecture capture choice.
- `SettingRow` renders one account or privacy preference.
- Route and page renderers remain framework-free TypeScript so this prototype adds no runtime dependency.

Each component now lives in its own descriptively named module under `frontend/src/renderer/components/`; the previous `ui_components.mts` monolith has been removed.

## Implemented source layout

```text
frontend/
├── index.html
├── src/
│   ├── main/index.ts
│   ├── preload/index.ts
│   └── renderer/
│       ├── index.mts
│       ├── app/
│       │   ├── router.mts
│       │   └── render_page.mts
│       ├── components/
│       │   ├── app_shell.mts
│       │   ├── consent_dialog.mts
│       │   ├── course_sidebar.mts
│       │   ├── lecture_card.mts
│       │   ├── lecture_timeline.mts
│       │   ├── login_navigation.mts
│       │   ├── metric_card.mts
│       │   ├── moment_detail.mts
│       │   ├── setting_row.mts
│       │   └── top_navigation.mts
│       ├── features/
│       │   ├── authentication/
│       │   ├── lecture-library/
│       │   ├── lecture-session/
│       │   ├── privacy-settings/
│       │   ├── professor-summary/
│       │   └── recovery-cards/
│       ├── fixtures/demo_content.mts
│       ├── types/backend_api.d.ts
│       └── styles.css
└── tests/
    ├── component/pages.test.cjs
    └── unit/router.test.cjs
```

This is the dependency-light implementation of the documented layout. React, Vite, hooks, stores, and service modules remain target architecture and should be introduced only through a separate reviewed migration.

## Interaction coverage

- Hash navigation between all prototype pages.
- Student and educator role switching.
- Explicit pre-lecture consent dialog.
- Lecture summary and transcript tabs.
- Selectable timeline moments with audience-specific details.
- Lecture-library search and status filtering.
- Login form validation.
- Educator summary export acknowledgment.
- Responsive sidebar and bottom navigation behavior.

## Data and integration state

All lecture, transcript, chart, account, and metric content is synthetic. The backend health check is the only existing service call; when the local FastAPI service is unavailable, the interface labels itself as demo mode.

The prototype does not add or change an API, shared schema, OpenAPI snapshot, or AsyncAPI contract. Live integration must use generated frontend types from the approved shared contracts rather than replacing fixture values with ad hoc payloads.

## Privacy and product language

- Raw system audio, camera frames, screenshots, and recordings stay on the device.
- The consent dialog does not begin capture automatically.
- Educator metrics are anonymous aggregates.
- The interface uses `lecture continuity`, `recovery hotspot`, and `possible missed-content moment`; it does not claim to prove attention, distraction, confusion, or comprehension.
- Evidence coverage includes a numerator and denominator.
- Delivery-quality observations are displayed separately from student-derived recovery signals.
- No individual student timeline, score, ranking, or identity is present.

## Follow-up integration

The live implementation should replace fixtures only after the related contract is approved and generated. It should add loading, empty, insufficient-evidence, suppressed-small-cohort, error, and deleted-session states at the same time.

**TEAM DECISION: Approve the final authenticated landing route and whether users may hold both student and educator roles.**

**TEAM DECISION: Approve the minimum anonymous group-size threshold before educator metrics connect to live data. The live UI must suppress results until this value is approved.**
