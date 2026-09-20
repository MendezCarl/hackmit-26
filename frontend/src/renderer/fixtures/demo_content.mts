/** Synthetic lecture fixtures used until approved API contracts are connected. */
export type LectureMoment = {
  momentId: string;
  startLabel: string;
  endLabel: string;
  startPercent: number;
  widthPercent: number;
  title: string;
  summary: string;
  evidence: string;
  action: string;
  severity: 'review' | 'notice';
};

export type LectureRecord = {
  lectureId: string;
  courseCode: string;
  courseTitle: string;
  lectureTitle: string;
  lectureDate: string;
  durationLabel: string;
  moments: LectureMoment[];
};

export const ACTIVE_LECTURE: LectureRecord = {
  lectureId: 'lecture-biology-cellular-respiration',
  courseCode: 'BIO 101',
  courseTitle: 'Foundations of Biology',
  lectureTitle: 'Cellular respiration and energy transfer',
  lectureDate: 'September 19, 2026',
  durationLabel: '52 minutes',
  moments: [
    {
      momentId: 'glycolysis-transition',
      startLabel: '12:40',
      endLabel: '14:05',
      startPercent: 24,
      widthPercent: 8,
      title: 'From glucose to pyruvate',
      summary:
        'Glycolysis converts one glucose molecule into two pyruvate molecules and produces a small amount of ATP before oxygen-dependent stages begin.',
      evidence: 'Aggregate recovery signals rose while the pathway diagram changed.',
      action: 'Revisit the carbon-count transition with one worked example.',
      severity: 'review',
    },
    {
      momentId: 'electron-carriers',
      startLabel: '27:40',
      endLabel: '29:12',
      startPercent: 52,
      widthPercent: 10,
      title: 'Electron carriers and the membrane',
      summary:
        'NADH and FADH₂ deliver high-energy electrons to protein complexes embedded in the inner mitochondrial membrane.',
      evidence: 'Audio clarity decreased and the slide changed twice in ninety seconds.',
      action: 'Check the microphone level and pause longer on the membrane diagram.',
      severity: 'notice',
    },
    {
      momentId: 'atp-synthase',
      startLabel: '41:10',
      endLabel: '43:00',
      startPercent: 78,
      widthPercent: 9,
      title: 'ATP synthase',
      summary:
        'The proton gradient powers ATP synthase, coupling movement across the membrane to ATP production.',
      evidence: 'Concept-check accuracy was 19 of 31 valid responses.',
      action: 'Add an analogy that separates the gradient from the enzyme it powers.',
      severity: 'review',
    },
  ],
};

export const LECTURE_LIBRARY: LectureRecord[] = [
  ACTIVE_LECTURE,
  {
    ...ACTIVE_LECTURE,
    lectureId: 'lecture-biology-cell-membranes',
    lectureTitle: 'Cell membranes and transport',
    lectureDate: 'September 17, 2026',
    durationLabel: '48 minutes',
  },
  {
    ...ACTIVE_LECTURE,
    lectureId: 'lecture-biology-enzymes',
    lectureTitle: 'Enzymes and reaction rates',
    lectureDate: 'September 15, 2026',
    durationLabel: '55 minutes',
  },
  {
    ...ACTIVE_LECTURE,
    lectureId: 'lecture-biology-water',
    lectureTitle: 'Water, pH, and buffers',
    lectureDate: 'September 12, 2026',
    durationLabel: '46 minutes',
  },
];

export const TRANSCRIPT_EXCERPTS = [
  {
    timeLabel: '12:40',
    speaker: 'Professor',
    text: 'At this point, each three-carbon molecule continues through the payoff phase, where ATP and NADH are produced.',
  },
  {
    timeLabel: '13:18',
    speaker: 'Professor',
    text: 'The important accounting step is that the pathway runs twice for every original glucose molecule.',
  },
  {
    timeLabel: '13:52',
    speaker: 'Professor',
    text: 'Keep the net total separate from the gross ATP made during the pathway.',
  },
];
