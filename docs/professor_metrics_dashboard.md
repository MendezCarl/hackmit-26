# Professor Metrics and Dashboard Plan

**Status:** Proposed feature plan  
**Owner:** Product and Education teams  
**Last updated:** 2026-09-20

## Purpose

Define the anonymous, aggregated metrics shown to professors after a lecture and how the dashboard turns those metrics into useful teaching actions.

The dashboard is a lecture-recovery tool, not an attention-policing system. It must describe model output as a possible missed-content signal rather than proof that a student was distracted, confused, attentive, or learning.

## Product principles

- Show professors where lecture material may need clarification.
- Prefer learning outcomes and recovery behavior over inferred attention.
- Separate student-derived recovery signals from lecture-delivery quality issues.
- Explain the evidence behind every AI-generated recommendation.
- Show participation coverage and denominators so professors can judge representativeness.
- Process raw audio, video, screenshots, and device signals locally.
- Share only approved, anonymous aggregates with professor-facing services.
- Never expose individual student timelines, rankings, or inferred attention scores.

## Recommended headline metrics

### Evidence coverage

Evidence coverage reports how much eligible, opted-in data contributed to the summary.

```text
evidence_coverage_ratio =
    participants_with_sufficient_data / eligible_opted_in_participants
```

Display the numerator and denominator with the ratio. For example: `68 of 82 opted-in participants contributed sufficient data (83%)`.

This metric must appear next to any lecture-wide result. A professor should not interpret a result without knowing how much of the class and lecture it represents.

### Lecture continuity

Lecture continuity replaces the proposed "attention ratio." It measures the percentage of valid lecture intervals that did not contain an aggregate recovery hotspot.

```text
lecture_continuity_ratio =
    valid_intervals_without_a_hotspot / all_valid_intervals
```

Lecture continuity does not claim to measure attention. A lower value means the system found more intervals that may deserve review.

**TEAM DECISION: Define the aggregation interval length. A 30- to 60-second starting interval is recommended for evaluation.**

**TEAM DECISION: Define the minimum evidence coverage required before lecture continuity is displayed.**

### Recovery hotspots

A recovery hotspot is a lecture interval where an approved percentage or count of participants produced possible missed-content signals.

Each hotspot should include:

- Lecture-relative start and end times in milliseconds.
- The topic, slide, or transcript segment associated with the interval.
- The number of eligible participants and the number contributing a signal.
- Signal duration and confidence.
- Supporting learning evidence when available.
- One recommended educator action.

Use labels such as `Recovery hotspot` or `Possible missed-content moment`. Do not label a hotspot as a distracted-student moment.

A hotspot should normally require evidence from at least two approved sources, such as:

- Aggregated local signal events plus low concept-check accuracy.
- Aggregated local signal events plus repeated recovery-card openings.
- A spike in anonymous student questions plus low confidence feedback.
- A delivery-quality problem plus a change in aggregated recovery signals.

**TEAM DECISION: Define the minimum anonymous group size. Until approved, the UI must suppress the metric rather than use an assumed threshold.**

**TEAM DECISION: Define the signal count, ratio, duration, and confidence required to create a hotspot.**

**TEAM DECISION: Decide whether every hotspot requires a second source of supporting evidence. Requiring corroboration is recommended.**

### Learning and recovery outcomes

When the product collects the necessary information, prioritize these outcomes over inferred behavior:

| Metric | Definition | Professor use |
| --- | --- | --- |
| Concept-check accuracy | Correct responses divided by valid responses for a concept | Identify concepts that need another example or explanation |
| Recovery-card open rate | Opened recovery cards divided by delivered recovery cards | Determine whether recovery material reached students |
| Recovery-card completion rate | Completed recovery cards divided by opened recovery cards | Evaluate whether students completed the intervention |
| Recovery helpfulness | Positive helpfulness responses divided by rated recovery cards | Evaluate the perceived usefulness of recovery content |
| Confidence change | Aggregated post-lecture confidence minus pre-lecture confidence | Identify concepts where students report improved or reduced confidence |
| Question themes | Anonymous questions grouped by concept | Find recurring uncertainty without identifying students |

Every ratio must display its numerator, denominator, measurement window, and missing-data state.

**TEAM DECISION: Decide whether the application collects pre- and post-lecture confidence ratings.**

**TEAM DECISION: Define what counts as opening and completing a recovery card.**

### Lecture delivery quality

Delivery-quality feedback must be presented separately from student-derived signals. The system may report observable technical conditions, including:

- Muffled, clipped, quiet, or noisy audio.
- The professor or demonstration moving outside the selected camera frame.
- Small slide text or low visual contrast.
- Low handwriting-recognition confidence.
- Blurry or obstructed screen sharing.
- Rapid slide changes or unusually fast speech that may reduce readability.

Each finding should contain:

1. The lecture interval.
2. The observable evidence and confidence.
3. The affected medium, such as audio, camera, slide, or handwriting.
4. A concrete suggested action.

Example:

> **Possible audio clarity issue — 27:40–29:12**  
> Speech-recognition confidence decreased while microphone volume became inconsistent.  
> **Suggestion:** Review this interval and consider repeating the explanation next lecture.

Do not make unsupported causal statements such as "students stopped paying attention because the microphone was muffled."

**TEAM DECISION: Approve the first delivery-quality detector allowlist and the confidence required to display each detector's output.**

## Dashboard presentation

### Summary row

Show no more than four primary cards:

1. `Lecture continuity`
2. `Evidence coverage`
3. `Recovery hotspots`
4. `Delivery issues`

Each card should include a plain-language definition or tooltip. Warning colors should communicate the need for review, not grade the professor or students.

### Lecture timeline

Display a shared lecture-time timeline with separate lanes for:

- Recovery hotspots.
- Delivery-quality issues.
- Concept or slide boundaries.
- Optional concept-check results.

Selecting a moment should open its evidence, associated topic, confidence, and suggested action. The timeline must not reveal individual student events.

### Moments to review

Present the highest-priority moments in a table with these columns:

| Column | Purpose |
| --- | --- |
| Time | Navigates to the lecture interval |
| Topic | Names the relevant concept or material |
| Evidence | Explains which aggregate signals support the finding |
| Coverage | Shows the contributing population and missing data |
| Suggested action | Gives the professor a concrete next step |
| Status | Allows the professor to review, dismiss, or resolve the finding |

Limit the default view to the most actionable three to five moments. The professor can expand the list when needed.

### Concept summary

Group results by concept and show:

- Aggregated recovery signals.
- Concept-check accuracy.
- Recovery helpfulness.
- Anonymous question themes.
- The system's suggested instructional response.

The dashboard should recommend actions such as reviewing a definition, adding another example, sharing a recovery resource, or revisiting a topic in the next lecture.

### Course trends

A secondary view may compare multiple lectures using:

- Recovery-hotspot frequency by concept.
- Recovery helpfulness over time.
- Recurring delivery-quality issues.
- Concept-check performance over time.
- Percentage of reports that met the approved evidence threshold.

Do not compare or rank individual students. Avoid a single opaque course-engagement score.

## AI-generated feedback requirements

AI-generated recommendations must:

- Use only allowlisted aggregate tools and approved course context.
- Cite the lecture interval and evidence used.
- Distinguish observation from suggestion.
- Report insufficient evidence instead of inventing an explanation.
- Allow the professor to dismiss or correct the result.
- Avoid diagnosing disability, emotion, motivation, or comprehension.
- Avoid claiming that a signal caused a learning outcome.

Provider orchestration and tool-calling behavior are defined in [AI Provider and Tool-Calling Implementation Plan](ai_provider_tool_calling_plan.md).

**TEAM DECISION: Decide whether AI recommendations are generated automatically after every lecture or only after professor review.**

**TEAM DECISION: Define whether professor corrections are retained and whether they may be used to evaluate or improve detectors.**

## Privacy and retention requirements

- Raw audio, video, screenshots, and device-level signals remain local.
- Professor reports contain anonymous aggregates only.
- Metrics are suppressed below the approved group-size threshold.
- Small cells must not be recoverable by filtering or combining dashboard views.
- Reports must not include student names, email addresses, device identifiers, or individual timelines.
- The interface must communicate opt-in coverage and excluded data.
- Deletion of a lecture must follow the team's approved retention and deletion behavior.

**TEAM DECISION: Approve the aggregate-report retention period and deletion behavior.**

**TEAM DECISION: Define which derived events may leave a student's device and whether privacy-preserving noise or additional aggregation is required.**

## API and contract implications

Implementation will require a versioned professor-summary contract containing:

- Lecture metadata and lecture-relative timestamps.
- Evidence coverage.
- Headline aggregate metrics.
- Recovery hotspots and supporting evidence references.
- Delivery-quality findings.
- Concept-level outcomes.
- AI suggestions and confidence metadata.
- Suppression and insufficient-data states.

The canonical payload must be added to [Unified API Contracts](api/unified_api_contracts.md), shared schemas, Pydantic response models, generated frontend types, and the OpenAPI snapshot together. Swagger UI must update from the FastAPI schema rather than from a separately maintained example in this document.

**TEAM DECISION: Approve the professor-summary endpoint shape and which roles are authorized to access it.**

## Implementation phases

### Phase 1: Definitions and synthetic dashboard

- Approve terminology, formulas, evidence thresholds, and suppression behavior.
- Build the dashboard with synthetic fixtures.
- Validate the layout and actions with educator team members.

### Phase 2: Local aggregation

- Aggregate approved local signal events into lecture intervals.
- Calculate evidence coverage and suppression states.
- Add tests for boundaries, missing data, and small cohorts.

### Phase 3: Summary API

- Add the shared professor-summary schema and FastAPI response model.
- Regenerate OpenAPI and frontend types.
- Use fake repositories and synthetic fixtures in default tests.

### Phase 4: Dashboard integration

- Connect the summary cards, timeline, moments table, and concept view.
- Add loading, empty, insufficient-data, error, and deleted-session states.
- Verify keyboard navigation, color contrast, and screen-reader labels.

### Phase 5: AI recommendations

- Expose only approved read-only aggregate tools to the selected AI provider.
- Validate recommendation output against a shared schema.
- Require evidence references and bounded confidence.
- Evaluate recommendations with educators before enabling them by default.

## Definition of done

- The dashboard never labels an output as verified attention, distraction, confusion, or comprehension.
- Professors can see evidence coverage and denominators.
- Recovery hotspots are anonymous, aggregated, and suppressed below the approved threshold.
- Delivery-quality issues are visually separated from student-derived signals.
- Every AI recommendation contains evidence and a lecture interval or reports insufficient evidence.
- Raw media never enters the professor-summary API or cloud-provider tool results.
- The API contract, Swagger documentation, shared schemas, frontend types, and tests agree.
- Educator team members validate that each primary metric leads to a practical teaching action.

