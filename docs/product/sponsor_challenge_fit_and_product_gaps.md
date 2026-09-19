# Sponsor Challenge Fit and Product Gaps

## Project concept

Build a compassionate lecture assistant that notices when a student may have missed part of a lecture, aligns that interval with the lecture transcript and visual context, and creates a concise recovery explanation. The product avoids punishing or labeling students for losing attention. Instead, it helps them recover the learning context they missed.

### Core experience

1. Capture lecture audio, optional screen content, and privacy-preserving student signals.
2. Detect a possible missed-content interval without claiming to measure a student's true attention.
3. Match that interval to timestamped transcript and slide context.
4. Generate a focused explanation of what the student likely missed.
5. Save the explanation, source material, and follow-up actions in a personal learning workspace.
6. Optionally provide professors with anonymous, aggregated class-level signals.

### Confirmed team context and requirements

- The team includes educators and already understands the student and professor user stories.
- Raw webcam frames, lecture audio, and captured media remain local on the user's device by default.
- System-audio capture is required.
- The ML/backend team owns the local signal rules and confidence thresholds.
- The ML/backend team owns the transcript-padding strategy.
- The team owns the data-retention and deletion policy.
- Zoom integration and a post-lecture professor metrics summary are core requirements, not optional stretch goals.

## Proposed tech stack

The stack below combines the original tools your team discussed with the missing infrastructure required to make the product work end to end.

| Layer | Technology | Responsibility |
|---|---|---|
| Desktop client | Electron | Cross-platform desktop wrapper with access to camera, microphone, and screen-capture permissions |
| Frontend | React + TypeScript | Student recovery cards, lecture timeline, professor dashboard, settings, and consent controls |
| Styling and visualization | Tailwind CSS + Recharts or Apache ECharts | Responsive UI and timestamped engagement/recovery visualizations |
| Camera capture | Browser `MediaDevices` API | Capture webcam frames locally with explicit user permission |
| Screen capture | Electron `desktopCapturer` or `getDisplayMedia()` | Capture lecture slides or the shared screen as optional learning context |
| Audio capture | Electron desktop capture + Web Audio API + `MediaRecorder` | Capture required system audio in timestamped chunks with operating-system permission handling |
| Local vision | MediaPipe + OpenCV | Face presence, approximate head pose, frame processing, and signal smoothing |
| Object detection | YOLO or a license-compatible detector | Optional phone/person detection; not required for the first MVP |
| Experimental video model | V-JEPA/V-JEPA 2 | Stretch goal for detecting temporal behaviors such as leaving the desk or pacing |
| Backend API | FastAPI + Python | Session orchestration, REST endpoints, WebSockets, transcript retrieval, and AI requests |
| Realtime transport | WebSockets | Stream transcript chunks, local detection events, session state, and live dashboard updates |
| Speech-to-text | Whisper/faster-whisper or Meta Muse Voice Transcribe | Convert lecture audio into timestamped transcript chunks |
| AI reasoning | OpenAI API | Generate grounded recovery cards from transcript, slide, timing, and course context |
| Primary database | MongoDB | Users, courses, lecture sessions, consent settings, recovery cards, and event metadata |
| Search and retrieval | Elasticsearch | Index transcripts, concepts, timestamps, slide text, and missed-content events for contextual retrieval |
| Cache and job queue | Redis | Cache repeated results, maintain short-lived session state, and queue background work |
| Background workers | RQ, Celery, or a lightweight Python worker | Run transcription, slide processing, retrieval, and summarization outside request handlers |
| Private media storage | Local application storage | Keep raw audio, screenshots, and optional recordings on-device; delete them according to the team's retention policy |
| Course content | Dropbox API | Read selected course files and write generated notes or review artifacts back to Dropbox |
| Zoom integration | Zoom Meeting SDK Electron wrapper + Zoom RTMS | Embed the Zoom meeting experience and access permitted live audio, video, screen-share, timestamps, and transcripts |
| Packaging and deployment | Docker + Docker Compose | Reproducible local services for FastAPI, Redis, MongoDB, Elasticsearch, and workers |
| Testing | Pytest + React Testing Library + Playwright | Backend unit tests, component tests, and end-to-end demo-flow validation |

### Technology roles and boundaries

- **MediaPipe and OpenCV** run on the student's device whenever possible. Raw webcam footage should not be uploaded to the backend.
- **YOLO** should be optional. Phone detection may create false assumptions and is not necessary to prove the compassionate recovery experience.
- **V-JEPA** is a research/stretch feature. The MVP should use simpler signals and temporal rules that the team can explain and test.
- **Redis** stores cache entries, current session state, and job references—not lecture recordings.
- **Local application storage** holds raw media. The cloud backend receives only the minimum derived data required for cross-user aggregation or AI processing.
- **Elasticsearch** is useful only if the team implements meaningful transcript and course-content retrieval. It should not replace MongoDB for accounts or application state.
- **OpenAI** receives the smallest relevant context window rather than the complete lecture. This supports privacy, speed, and the Token Company challenge.
- **Dropbox access** should be limited to folders and files the student explicitly selects.

### What “object storage” meant

Object storage—such as Amazon S3 or MinIO—would mean storing media files such as lecture audio, screenshots, or recordings in a cloud bucket or a self-hosted equivalent. It is not required for this product. Because the team has chosen a privacy-first local-media design, raw media should remain in an app-managed directory on the student's device and should not be uploaded by default.

The backend can still receive smaller derived artifacts when required, such as:

- timestamped transcript text selected for an AI request;
- coarse events such as `face_absent` or `window_unfocused`;
- an anonymous aggregate count for a professor metric window;
- generated recovery cards; and
- user-selected notes or review artifacts written to Dropbox.

If the team later adds cloud backup, it should be opt-in and separate from the core architecture.

Keeping raw media local does not make the entire system offline. Zoom RTMS delivers meeting data through Zoom's service, OpenAI processes the selected context sent for recovery generation, and Dropbox stores only the derived artifacts the user chooses to sync. The privacy goal is therefore **data minimization**: never upload raw student webcam media and send each external service only what its feature requires.

## End-to-end architecture

```text
Electron client + Zoom Meeting SDK
├── Webcam → MediaPipe/OpenCV → local timestamped signals
├── System audio → local timestamped chunks
└── Local app storage → temporary raw media
             │
             └── anonymous time-bucket events ─────────┐
                                                       │
Zoom meeting → Zoom RTMS                               │
└── permitted transcript/audio/screen-share/timeline ──┤
                                                       ▼
                                            FastAPI + WebSockets
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
     MongoDB metadata    Redis queue/cache   Background worker
            │                 │                 │
            └──────────┬──────┴─────────────────┘
                       ▼
              Elasticsearch retrieval
                       │
              ┌────────┴────────┐
              ▼                 ▼
       Dropbox course files   OpenAI API
              └────────┬────────┘
                       ▼
              Grounded recovery card
                       │
          ┌────────────┴──────────────────┐
          ▼                               ▼
    Student dashboard       Anonymous post-lecture summary
```

## Central timestamp model

The timestamped event timeline is the most important architectural concept. Every service must refer to the same lecture session clock.

```json
{
  "lecture_id": "cs-os-lecture-04",
  "event_type": "possible_missed_window",
  "start_ms": 931200,
  "end_ms": 978700,
  "signals": ["face_absent", "window_unfocused"],
  "confidence": 0.76,
  "user_confirmed": null
}
```

Transcript chunks, slide changes, student events, and recovery cards should all use the same `lecture_id`, `start_ms`, and `end_ms` convention. This allows the backend to answer the central product question: **What was being taught during the interval the student may have missed?**

## Recommended hackathon stack

The full architecture is larger than a weekend build. For the working MVP, use:

| Requirement | MVP choice |
|---|---|
| Desktop experience | Electron + React + TypeScript |
| Attention-related signals | MediaPipe face presence/head pose with simple time-based rules |
| Lecture capture | Required system-audio capture through Electron desktop capture + Web Audio/MediaRecorder |
| Zoom meeting | Zoom Meeting SDK Electron wrapper |
| Zoom media/timeline | Zoom RTMS |
| Transcription | RTMS transcript for Zoom mode; local faster-whisper or Muse Voice Transcribe for non-Zoom mode |
| Backend | FastAPI + WebSockets |
| Application data | MongoDB |
| Short-lived state and caching | Redis |
| AI recovery explanation | OpenAI API with structured output |
| Course materials | Dropbox API for a user-selected folder |
| Deployment | Docker Compose |
| Validation | Pytest plus one Playwright end-to-end demo test |

For the MVP, raw media remains local. Zoom integration and the post-lecture professor summary are part of the core flow. Add Elasticsearch only after basic timestamp retrieval works. Treat V-JEPA, YOLO, and public-dataset research as stretch work.

## Zoom support for this product

Yes. Zoom supports the proposed product, but the implementation should use two complementary Zoom technologies:

1. **Zoom Meeting SDK Electron wrapper:** embeds the Zoom meeting experience in the Electron app. Zoom officially supports an Electron wrapper, but its documentation and developer support are limited; Zoom recommends its native macOS or Windows Meeting SDKs for most integrations.
2. **Zoom Realtime Media Streams (RTMS):** provides the live data pipeline. RTMS exposes permitted meeting audio, video, screen share, transcript data, timestamps, meeting metadata, participant join/leave events, and diarized transcript segments. It is a better fit than trying to extract all media through the UI layer.

Official documentation:

- [Zoom Meeting SDK overview](https://developers.zoom.us/docs/meeting-sdk/)
- [Zoom Meeting SDK Electron wrapper](https://developers.zoom.us/docs/meeting-sdk/electron/)
- [Zoom RTMS overview](https://developers.zoom.us/docs/rtms/meetings/)
- [Zoom RTMS setup and prerequisites](https://developers.zoom.us/docs/rtms/meetings/getting-started/)
- [Zoom RTMS disclosure and host-approval experience](https://developers.zoom.us/docs/rtms/meetings/ux-overview/)

### Recommended Zoom flow

1. The student joins through the embedded Meeting SDK experience.
2. The Electron client analyzes the student's webcam locally and creates timestamped signals; raw webcam frames never leave the device.
3. Required system audio is captured locally. Separately, RTMS sends permitted Zoom audio, transcript, screen-share, and meeting timeline data to the application's RTMS receiver/backend.
4. The app aligns local student events to the RTMS meeting timeline.
5. During the lecture, the client sends only coarse, anonymous event counts to the backend in time buckets.
6. When the RTMS stream or meeting ends, the backend aggregates those buckets and produces the professor's post-lecture summary.
7. The professor sees class-level patterns such as “many students may have missed context during 34:10–36:05,” not individual student scores.

RTMS access is not invisible: an app requests access, the host can approve or deny it, and Zoom displays an active-app disclosure to participants. RTMS also requires Zoom Developer Pack credits. These constraints should be incorporated into the demo and deployment plan.

### Post-lecture professor summary

Zoom supplies the session timeline, transcript/media streams, participant join/leave events, and meeting metadata. It does **not** produce the product's attention or engagement score. The team's local ML pipeline creates privacy-preserving signals, and the product combines their anonymous aggregates with the Zoom lecture timeline.

A useful end-of-lecture report can contain:

- a time-series chart of the percentage of participating devices that emitted a possible missed-content signal;
- the three lecture intervals with the highest anonymous signal rate;
- the topic being discussed during each interval, derived from the RTMS transcript;
- aggregate signal categories such as `face_absent`, `head_away`, or `window_unfocused`;
- participant join/leave context from RTMS so normal exits are not confused with missed content; and
- a suggested instructor action, such as revisiting a concept or sharing the related recovery card.

The report should not contain student names, individual attention percentages, raw webcam frames, or raw local audio. Metrics should appear only after the team-selected minimum participation threshold is met.

## Confirmed ownership and remaining team decisions

The following items are already settled or have a clear team owner:

- Educators on the team own and validate the user story.
- Local device storage is the default for raw media.
- System-audio capture is required.
- The ML/backend team owns local signal rules and thresholds.
- The ML/backend team owns transcript-padding behavior.
- The team owns data-retention and deletion behavior.
- Zoom integration and the post-lecture summary are required.

Everything that still requires an explicit team decision is bolded below:

- **Choose the non-Zoom transcription path: local faster-whisper or Meta Muse Voice Transcribe.** Zoom mode can use RTMS transcripts.
- **Decide whether Elasticsearch is necessary for the hackathon MVP or whether MongoDB timestamp queries are sufficient.**
- **Define the structured OpenAI input and recovery-card output schemas.**
- **Define the cache key and invalidation strategy for transcript segments and recovery cards.**
- **Decide whether derived transcript excerpts sent to OpenAI are processed ephemerally only or also saved locally as part of the recovery-card history.**
- **Decide whether professor metrics are computed entirely on-device and uploaded as final aggregates, or computed by the backend from anonymous time-bucket events.**
- **Set the minimum number of participating students required before the professor can see an aggregate metric.**
- **Choose the time-bucket resolution for professor metrics, such as 10, 15, or 30 seconds.**
- **Decide whether the Electron Meeting SDK wrapper is acceptable despite limited Zoom documentation/support, or whether a native macOS/Windows Meeting SDK client is needed after the hackathon.**
- **Confirm access to Zoom Developer Pack credits, required RTMS scopes, host approval, and the participant disclosure flow before the demo.**
- **Verify licenses for the exact YOLO implementation, model weights, and any public datasets used.**
- **Select a qualifying public dataset before committing to the Voloridge challenge.**

## Executive assessment

The percentages below represent **challenge fit**, not the probability of winning.

| Sponsor | Current fit | Fit after closing gaps | Largest gap |
|---|---:|---:|---|
| OpenAI | 82% | 96% | OpenAI must power reasoning, not just generic summarization; the team must also demonstrate meaningful Codex usage |
| Long Lake | 88% | 95% | The team needs a polished skeptic-focused experience and evidence that users would return |
| Dropbox | 62% | 91% | Dropbox content must become a core source of persistent learning context and actions |
| The Token Company | 68% | 92% | The team must benchmark token usage and demonstrate measurable cost savings |
| Meta | 55% | 82% | The product currently helps an individual more than it strengthens human connection |
| Ramp | 50% | 78% | Time savings are clear, but money savings are not yet credible or measurable |
| Voloridge | 35% | 74% | The current product does not use a real-world public dataset, which the challenge requires |

## 1. OpenAI Challenge

### Challenge summary

Use the OpenAI API to build an ambitious product, with Codex acting as a development teammate. Judges assess both the product's use of the OpenAI API and the team's concrete use of Codex for planning, implementation, testing, debugging, or iteration.

### Why the product fits

OpenAI can serve as the reasoning layer that reconstructs the learning context a student missed. It can combine the missed interval, nearby transcript, slide image, course context, and later references to explain the important concepts rather than merely summarize a block of text.

### Current product gaps

- The OpenAI feature is currently described too broadly as “summarize missed information.”
- **The team must define the structured input sent to the model.**
- There is no defined output schema for recovery cards.
- The team has not shown how the model will cite or connect explanations to the original transcript and slide.
- There is no evaluation plan for summary accuracy, completeness, or hallucinations.
- There is no documented example of how Codex materially improved the build.
- The local-media privacy boundary is established, but the team still needs to ensure that only the minimum transcript and slide context is sent to the model.

### Product additions needed

- Use local computer vision to create timestamps, not identity or emotion labels.
- Send only relevant transcript segments and selected slide images to the OpenAI API.
- Use structured output with fields such as:
  - `topic`
  - `what_you_missed`
  - `key_facts`
  - `example_from_lecture`
  - `source_timestamps`
  - `follow_up_question`
- Add grounded source links that jump back to the supporting transcript or lecture moment.
- Create a small evaluation set containing missed intervals and human-written reference explanations.
- Record concrete Codex contributions such as architecture design, generated tests, debugging a timestamp bug, or improving prompts after evaluation failures.

### Winning demo evidence

- Show a student leaving or looking away during a lecture segment.
- Show the exact timestamped transcript and slide context retrieved.
- Show OpenAI generating a grounded recovery card with source timestamps.
- Ask one follow-up question about the missed concept.
- Show one before-and-after example where Codex helped the team detect and fix a real product issue.

## 2. Long Lake — Convince a Non-Believer

### Challenge summary

Create an AI product or experience that a skeptic would try, love, and want to use again. The experience should reveal a practical value of frontier AI to someone who has not yet found AI useful.

### Why the product fits

The “I walked away and the app caught me up” moment is immediate, personal, and easy to understand. It does not require users to learn prompt engineering or change how they study before receiving value.

### Current product gaps

- The educator-led team understands the user story, but that understanding still needs to be translated into a concise skeptic-focused demo narrative.
- The product still risks looking like another surveillance or attention-scoring tool.
- The team has not yet demonstrated why AI is necessary instead of a simple timestamped transcript.
- The recovery flow may contain too much setup before the useful moment appears.
- There is no evidence that users would return after the first demonstration.
- The professor dashboard could distract from the strongest student-centered story.

### Product additions needed

- Translate the educator-validated user story into one concise skeptic persona for the demo—for example, a student who dislikes AI chatbots and sometimes misses lecture details.
- Make the first-value moment happen in one click or automatically after the student returns.
- Use compassionate language such as “You may have missed…” rather than “You were inattentive.”
- Let the student correct false detections and disable specific signals.
- Show why the AI output is better than transcript search by identifying the concept, explaining it at the student's level, and surfacing the exact supporting moment.
- Add repeat value through a review queue of missed concepts across multiple lectures.

### Winning demo evidence

- Start with the skeptic's problem, not the architecture.
- Demonstrate the entire magic moment in under 45 seconds.
- Show a recovery card that is visibly more helpful than replaying or searching the full lecture.
- Include a short user quote or test showing that a skeptical student would use it again.

## 3. Dropbox Challenge

### Challenge summary

Turn messy digital content into something organized, understandable, or actionable. The prompt specifically includes transforming class materials into a personalized tutor and creating new ways to organize, discover, and act on digital content.

### Why the product fits

Students already have fragmented slides, syllabi, readings, notes, recordings, and transcripts. The lecture assistant can connect a missed moment to those materials and turn them into explanations, review tasks, and a persistent learning memory.

### Current product gaps

- Dropbox is not currently part of the core workflow.
- The current idea focuses on live recovery rather than fragmented files and content organization.
- There is no ingestion, file-selection, synchronization, or permission flow.
- There is no unified content model connecting a class, lecture, transcript, slide deck, notes, and recovery cards.
- The system does not yet turn recovered information into durable actions.
- Raw media remains local, but **the team must decide which derived artifacts—recovery cards, review notes, flashcards, or transcript excerpts—are written to Dropbox.**

### Product additions needed

- Let students select a Dropbox course folder containing slides, readings, notes, and assignments.
- Ingest files with user consent and retain their Dropbox source references.
- Connect every recovery card to the relevant lecture file, slide, note, or reading.
- Save generated review notes or a missed-concepts report back to Dropbox.
- Add actions such as:
  - create a review checklist;
  - generate flashcards from missed concepts;
  - find the supporting slide or reading;
  - compare the professor's explanation with the student's notes.
- Organize content by course, lecture, concept, and source rather than relying only on folders.

### Winning demo evidence

- Begin with a messy Dropbox course folder.
- Detect a missed lecture interval.
- Retrieve the relevant lecture transcript and slide deck.
- Produce an explanation grounded in those files.
- Save an actionable review artifact back into the student's course folder.

## 4. The Token Company — LLM Cost Saving Challenge

### Challenge summary

Demonstrate creative and measurable savings in the LLM stack through smaller inputs, caching, cheaper models, dense outputs, compression, or another cost-reduction technique. Savings must occur inside the product rather than only during development.

### Why the product fits

The timestamped missed interval provides a natural way to avoid sending an entire lecture to a model. The product can retrieve only the missed section plus limited surrounding context, cache repeated summaries, and use cheaper models for low-risk preprocessing.

### Current product gaps

- There is no measured baseline for tokens, latency, or cost.
- **The ML/backend team must tune how much surrounding transcript context is sufficient.**
- **The team must define the cache-key and invalidation strategy.**
- The architecture does not yet route simple and difficult cases to different models.
- Repeated students in the same lecture could trigger duplicate model calls.
- The product does not yet expose its cost savings in the demo.

### Product additions needed

- Establish a naive baseline: send the full lecture transcript for every recovery request.
- Implement time-window retrieval around each missed interval.
- Merge overlapping missed intervals before calling the model.
- Cache lecture-segment summaries using lecture ID, transcript version, interval, slide version, and prompt version.
- Generate a shared factual segment summary once, then personalize it cheaply for each student.
- Route easy cases to a smaller model and reserve a stronger model for ambiguous or multimodal segments.
- Test The Token Company's compression model if it improves cost without materially reducing answer quality.
- Build a cost dashboard comparing baseline and optimized token counts, dollars, cache hit rate, and latency.

### Winning demo evidence

- Run the same recovery request through both the baseline and optimized pipelines.
- Show actual measured input/output tokens, latency, and estimated cost.
- Demonstrate a cache hit for a second student who missed the same segment.
- Include a small quality evaluation showing that savings did not meaningfully harm the recovery explanation.

## 5. Meta — Bringing People Closer Together with AI

### Challenge summary

Build an AI-powered social product that meaningfully strengthens human connection. AI must be essential and well integrated. The submission also requires a working prototype, a two- to three-minute demo video, a public repository, and a short explanation of who the product serves, how it strengthens connection, and why AI is essential.

### Why the product can fit

The project can improve the feedback loop between students and professors. Anonymous, aggregated signals can help a professor identify concepts that many students may have lost track of and respond with clarification, while students can safely request help without public embarrassment.

### Current product gaps

- The primary experience currently improves individual learning rather than human connection.
- A numerical “attention ratio” could create surveillance instead of trust.
- The product does not yet enable meaningful professor-student or peer interaction.
- **The team must set the minimum participation threshold for anonymous aggregation.**
- The reason to use Meta's models or APIs is not defined.
- The product could unintentionally penalize neurodivergent students, students with disabilities, or students whose listening behavior differs from visual assumptions.

### Product additions needed

- Replace individual attention scores with anonymous “possible confusion or missed-context” windows.
- Only reveal class-level information after a minimum group threshold is met.
- Allow students to voluntarily send an anonymous “please revisit this concept” signal.
- Let professors post a clarification tied to the exact lecture moment; deliver it to affected students.
- Add an optional peer study-room feature that groups students around concepts they chose to review—not around inferred deficiencies.
- Consider Muse Voice Transcribe for realtime lecture transcription if it meaningfully supports the experience.
- Publish a clear privacy statement: raw student video stays local and professors never receive individual behavioral data.

### Winning demo evidence

- Several students encounter difficulty around the same concept.
- The professor receives an anonymous, aggregate signal—not student identities.
- The professor posts a clarification or schedules a review.
- Students receive the clarification and optionally connect in a concept-based study group.

## 6. Ramp — Save Time. Save Money.

### Challenge summary

Build anything that saves people time and money.

### Why the product can fit

The product can reduce time spent scrubbing through recordings, rereading entire chapters, or searching scattered files for a missed explanation. A stronger submission can also show institutional or student cost savings.

### Current product gaps

- Time savings are intuitive but not measured.
- Money savings are currently speculative.
- The project does not compare its workflow against a credible alternative.
- Expensive transcription, storage, vision, and LLM calls could weaken the savings claim.
- The professor dashboard does not yet demonstrate avoided reteaching or support workload.

### Product additions needed

- Instrument time-to-recover for:
  - manually scrubbing a recording;
  - searching a transcript;
  - using the recovery card.
- Add a calculator showing minutes saved per missed interval, class, and semester.
- Measure how shared segment summaries and caching reduce the product's own operating costs.
- For instructors, track repeated questions or concepts that can be clarified once for the entire class.
- Avoid claiming tuition or grade-related savings unless the team has defensible evidence.

### Winning demo evidence

- Give a participant the same missed concept using a recording and the recovery assistant.
- Measure and display the difference in completion time.
- Convert the measured minutes into a conservative semester estimate.
- Pair the user time savings with the Token Company cost-optimization metrics.

## 7. Voloridge — Signal in the Noise

### Challenge summary

Build an original and technically strong project using one or more real-world public datasets. Extract meaningful insight, discover patterns, create useful analysis or visualizations, train models, combine datasets, or process large datasets efficiently.

### Why the product only partially fits today

The product already searches for useful signals inside noisy, multimodal lecture data. However, it currently generates its own webcam and lecture data. The challenge explicitly requires at least one real-world public dataset, so the current architecture does not satisfy the central requirement.

### Current product gaps

- No qualifying public dataset is integrated.
- **The team must identify a research question that a public dataset helps answer.**
- There is no dataset cleaning, exploration, or insight-generation component.
- A generic pre-trained attention model would not be enough if the public data is not central to the product.
- Public “engagement” labels may be biased, subjective, or collected without conditions matching the product.
- The current demo emphasizes a single user interaction rather than large-scale data processing or discovery.

### Product additions needed

- **Select a public lecture, education, gaze, classroom-behavior, or video-understanding dataset with a license that permits the intended use.**
- **Define a narrow Voloridge research question**, such as:
  - Which observable events are reliable enough to flag a possible missed-content window?
  - How do head-pose, face-presence, and interaction signals vary across different learning settings?
  - Can multiple weak signals outperform a single gaze-based rule while reducing false positives?
- Audit the dataset's demographics, collection setting, labels, and biases.
- Train or evaluate the missed-window detector on the public dataset.
- Report precision, recall, false-positive rate, and subgroup limitations where the data allows it.
- Create an interactive visualization of the noisy signals, detected intervals, and model uncertainty.
- Keep the model's conclusion probabilistic: “possible missed-content window,” never “student is inattentive.”

### Winning demo evidence

- Explain the public dataset and why it is relevant.
- Show the cleaning or feature pipeline and one non-obvious insight discovered.
- Compare at least two detection approaches.
- Visualize where the model succeeds, fails, and expresses uncertainty.
- Show how the dataset-derived insight improves the live product.

### Go/no-go condition

Do not submit to Voloridge unless the team can identify a credible public dataset early and make it central to a meaningful analysis. Adding a public dataset at the end only for eligibility will weaken the project.

## Consolidated product gaps

### Must close for the core product

- Build one synchronized timeline for transcript chunks, slides, student events, and recovery cards.
- Add realtime speech-to-text and timestamped transcript storage.
- Enforce the privacy boundary: raw webcam data stays local; only coarse events leave the device.
- Replace definitive attention labels with uncertainty-aware missed-content signals.
- Design grounded recovery cards with source timestamps.
- Add evaluation for detection quality and explanation quality.
- Implement consent, data retention, deletion, and recording indicators.

### Must close for the selected sponsor strategy

- **OpenAI:** structured multimodal reasoning, grounding, evaluation, and documented Codex contribution.
- **Long Lake:** polished skeptic-focused magic moment and evidence of repeat value.
- **Dropbox:** real course-folder ingestion, source-aware organization, and actions written back to files.
- **Token Company:** measured baseline, retrieval, caching, routing, and cost dashboard.
- **Meta:** an opt-in human feedback loop with aggregate privacy protections.
- **Ramp:** measured time saved and a conservative, defensible money-saving story.
- **Voloridge:** a qualifying public dataset, clear research question, analysis, and measurable insight.

## Recommended build priority

### Priority 0 — Foundation

1. Electron client captures audio and local webcam signals.
2. Realtime transcription produces timestamped chunks.
3. A missed-content detector creates uncertain, editable intervals.
4. The backend retrieves the interval plus limited surrounding context.
5. OpenAI generates a grounded recovery card.
6. The student can jump to sources and ask a follow-up question.

### Priority 1 — Highest-value sponsor work

1. Instrument token, latency, and cost metrics.
2. Add context-window retrieval, interval merging, and caching.
3. Polish the Long Lake “return and recover” demonstration.
4. Document how Codex helped build, test, and improve the system.

### Priority 2 — Persistent learning workspace

1. Connect a Dropbox course folder.
2. Retrieve slides, readings, and notes as supporting context.
3. Save review notes or tasks back to Dropbox.

### Priority 3 — Human connection

1. Add voluntary student feedback.
2. Aggregate signals only above a privacy threshold.
3. Let professors issue a clarification connected to a lecture moment.

### Priority 4 — Optional challenge expansions

1. Add the Ramp time-savings experiment and calculator.
2. Pursue Voloridge only after selecting and validating a suitable public dataset.

## Suggested challenge submission strategy

### Primary targets

- **OpenAI:** strongest technical core and reasoning story.
- **Long Lake:** strongest product story and live demo moment.
- **The Token Company:** natural optimization layer with measurable results.
- **Dropbox:** strong expansion if the persistent learning workspace is functional.

### Secondary targets

- **Meta:** submit only if the professor-student clarification loop is working and privacy-safe.
- **Ramp:** submit if the team has real time-savings measurements and a defensible money component.

### Conditional target

- **Voloridge:** submit only if a public dataset materially shapes the model or analysis.

## Final positioning

> Students lose attention for ordinary human reasons. Instead of monitoring, shaming, or punishing them, our system privately detects when they may have missed something, reconstructs the lost learning context from the lecture and course materials, and helps students and professors reconnect around the concepts that need clarification.

That positioning keeps the product compassionate while giving each selected sponsor a legitimate role rather than attaching unrelated features solely for eligibility.
