"""Canonical synthetic lecture data used by the demo runner and e2e tests.

Everything in this module is synthetic; it contains no real student data,
transcripts, or media. The missed interval matches the timestamp model from
the product plan.
"""

from __future__ import annotations

from app.contracts.models import SignalEvent, TranscriptChunk, TranscriptSource

DEMO_LECTURE_ID = "demo-lecture-0001"
DEMO_COURSE_ID = "demo-course-101"
DEMO_SESSION_TITLE = "Synthetic Lecture: Attention and Transformers"

# The central timestamp model's example interval.
MISSED_WINDOW_START_MS = 931_200
MISSED_WINDOW_END_MS = 978_700
PARTICIPANT_COUNT = 5
SPEAKER_LABEL = "instructor"


def build_synthetic_transcript_chunks(session_id: str) -> list[TranscriptChunk]:
    """Build the canonical synthetic timestamped transcript.

    Args:
        session_id: Session the synthetic chunks belong to.

    Returns:
        Final synthetic transcript chunks covering the missed interval.
    """

    synthetic_lines = [
        (
            900_000,
            930_000,
            (
                "Before we continue, recall that attention lets a model weigh how "
                "much each input token should influence every output token."
            ),
        ),
        (
            930_000,
            960_000,
            (
                "We compute attention scores by taking a query vector and "
                "measuring its similarity against every key vector. "
                "A softmax then turns those scores into weights that sum to one."
            ),
        ),
        (
            960_000,
            990_000,
            (
                "Multi-head attention runs several of these scoring passes in "
                "parallel so the model can track different relationships at once."
            ),
        ),
        (
            990_000,
            1_020_000,
            (
                "Finally, the weighted values are concatenated and projected back "
                "into the original embedding size before the next layer begins."
            ),
        ),
    ]
    return [
        TranscriptChunk(
            chunk_id=f"demo-chunk-{index}",
            session_id=session_id,
            start_ms=start_ms,
            end_ms=end_ms,
            text=text,
            speaker_label=SPEAKER_LABEL,
            source=TranscriptSource.LOCAL_TRANSCRIPTION,
            is_final=True,
            revision=1,
        )
        for index, (start_ms, end_ms, text) in enumerate(synthetic_lines, start=1)
    ]


def build_synthetic_missed_event(session_id: str, event_id: str) -> SignalEvent:
    """Build one synthetic possible-missed-window event.

    Args:
        session_id: Session the event belongs to.
        event_id: Unique synthetic event identifier.

    Returns:
        A synthetic coarse signal event matching the central timestamp model.
    """

    return SignalEvent(
        event_id=event_id,
        session_id=session_id,
        event_type="possible_missed_window",
        start_ms=MISSED_WINDOW_START_MS,
        end_ms=MISSED_WINDOW_END_MS,
        signals=["head_away", "window_unfocused"],
        confidence=0.76,
        user_confirmed=None,
        client_generated_at=None,
    )


FULL_LECTURE_END_MS = 1_800_000


def build_full_lecture_chunks(session_id: str) -> list[TranscriptChunk]:
    """Return a synthetic thirty-minute lecture with distinct surrounding topics.

    Args:
        session_id: Synthetic running session receiving the final chunks.

    Returns:
        Ordered chunks: introduction, the attention example, and practice.
    """
    chunks = build_synthetic_transcript_chunks(session_id)
    for start in [
        *range(0, 900_000, 60_000),
        *range(1_020_000, FULL_LECTURE_END_MS, 60_000),
    ]:
        text = BACKGROUND_SEGMENTS[len(chunks) - 4]
        chunks.append(
            TranscriptChunk(
                chunk_id=f"demo-context-{start}",
                session_id=session_id,
                start_ms=start,
                end_ms=start + 60_000,
                text=text,
                speaker_label=SPEAKER_LABEL,
                source=TranscriptSource.LOCAL_TRANSCRIPTION,
                is_final=True,
                revision=1,
            )
        )
    return sorted(chunks, key=lambda chunk: chunk.start_ms)


# Distinct synthetic excerpts avoid inflating the comparison by repeating filler.
BACKGROUND_SEGMENTS = (
    "Today we will connect vector representations, attention, and transformer blocks. Keep a small example sentence nearby as we work through each stage.",
    "A tokenizer splits text into the units the model processes. A token may be a word, part of a word, or punctuation, depending on the vocabulary.",
    "Each token receives an embedding vector. The coordinates are learned during training and give later layers a numerical representation to transform.",
    "A matrix collects several vectors into rows. Before multiplying matrices, check that the inner dimensions match and predict the output shape.",
    "The dot product multiplies matching coordinates and adds their products. It is a building block for the similarity scores we will use later.",
    "Vector magnitude affects a dot product as well as direction. Similarity scores therefore depend on how representations are formed and scaled.",
    "A learned linear projection changes the coordinates of a representation. Different projections can expose different relationships in the same input.",
    "Batching groups several examples for computation. Keep the batch dimension distinct from the number of tokens and the embedding width.",
    "Token order matters in a sentence. Position information helps a transformer distinguish sequences that contain the same words in a different order.",
    "Some batches contain padding so examples have compatible shapes. A padding mask prevents those artificial positions from influencing a prediction.",
    "A causal mask restricts access to future tokens during next-token prediction. The prediction at a position can use only permitted earlier context.",
    "Softmax maps a list of real scores to positive weights summing to one. Increasing one score changes its weight relative to the other scores.",
    "Consider the pronoun in a short sentence. Its useful context may be several words away, so a fixed neighboring window can miss the relationship.",
    "Queries express what a position is seeking, keys support matching, and values carry information to combine. All three are learned projections.",
    "Track the dimensions of queries, keys, and values on paper. We are now ready to connect similarity scores with a weighted combination of values.",
    "A residual connection adds a block's input to a transformed result. Matching dimensions makes that addition possible throughout the network.",
    "Normalization controls the scale of intermediate representations. Its position within a transformer block depends on the architecture being used.",
    "A feed-forward sublayer transforms each token representation. It complements the cross-token information exchange performed by attention.",
    "Stacking transformer blocks lets later layers operate on increasingly contextual representations. Each layer still receives structured vectors.",
    "The training objective specifies the prediction task. For next-token training, predicted probabilities are compared with the actual next token.",
    "Cross-entropy penalizes assigning low probability to the reference token. Averaging over examples produces a training signal for parameter updates.",
    "Backpropagation computes gradients of the loss with respect to parameters. An optimizer uses those gradients to update the learned projections.",
    "Keep evaluation examples separate from training data. A lower training loss alone does not establish that the model generalizes to new examples.",
    "Inspect errors as well as an overall evaluation metric. Examples with similar aggregate scores can fail in different and practically significant ways.",
    "Attention weights are internal computation values. They should not automatically be treated as a complete explanation of why a model answered.",
    "Longer sequences increase the work performed by standard dense attention. Restricting relevant context can reduce input size in an application.",
    "For the practice exercise, label the shapes at each step and explain which positions can interact. Use the mask to justify each allowed connection.",
    "Our recap connects token embeddings, projected queries and keys, normalized weights, and combined values. Bring any uncertain step to the next discussion.",
)
