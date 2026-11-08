"""T35: speaker names. Deepgram labels each word `SPEAKER_00`, `SPEAKER_01`, ...; a person
names them once (`post transcript speakers <id> --map SPEAKER_00="a podcast host"`, or a click on
a speaker label in the editor) and the name shows everywhere that label does. Names are
stored on the transcript (`Transcript.speakers`), never baked into word text.

`summary` gives each speaker's word count and a sample to identify them by ear: their longest
utterance (the longest unbroken run of their words), which the editor plays from the audio
proxy.
"""
from __future__ import annotations

from pathlib import Path

from ...model.transcript import Transcript, Word
from ...store import store as store_module
from ...store.errors import RevisionConflict

SAMPLE_TEXT_WORDS = 40
WRITE_ATTEMPTS = 5


class UnknownSpeaker(ValueError):
    """A name was given for a label the transcript doesn't use (usually a typo)."""


def labels(transcript: Transcript) -> list[str]:
    """Every speaker label, in order of first appearance."""
    seen: dict[str, None] = {}
    for word in transcript.words:
        if word.speaker:
            seen.setdefault(word.speaker, None)
    return list(seen)


def _utterances(words: list[Word]) -> list[tuple[str, int, int]]:
    """Maximal runs of consecutive words by one speaker: `(label, first, last)` indexes."""
    runs: list[tuple[str, int, int]] = []
    for i, word in enumerate(words):
        if runs and runs[-1][0] == word.speaker:
            runs[-1] = (word.speaker, runs[-1][1], i)
        else:
            runs.append((word.speaker, i, i))
    return [r for r in runs if r[0]]


def summary(transcript: Transcript) -> list[dict]:
    """`[{label, name, words, sample: {start, end, text}}]`, one per speaker, in order of
    first appearance. `name` is None until someone names them."""
    words = transcript.words
    counts: dict[str, int] = {}
    for word in words:
        if word.speaker:
            counts[word.speaker] = counts.get(word.speaker, 0) + 1
    longest: dict[str, tuple[int, int]] = {}
    for label, first, last in _utterances(words):
        best = longest.get(label)
        if best is None or words[last].end - words[first].start > words[best[1]].end - words[best[0]].start:
            longest[label] = (first, last)
    out = []
    for label in labels(transcript):
        first, last = longest[label]
        run = words[first:last + 1]
        text = " ".join(w.text for w in run[:SAMPLE_TEXT_WORDS]) + (" …" if len(run) > SAMPLE_TEXT_WORDS else "")
        out.append({
            "label": label, "name": transcript.speakers.get(label), "words": counts[label],
            "sample": {"start": words[first].start, "end": words[last].end, "text": text},
        })
    return out


def set_names(root: str | Path, transcript_id: str, names: dict[str, str]) -> Transcript:
    """Name (or, with an empty name, un-name) speakers on one transcript. Refuses a label
    the transcript doesn't use, naming the ones it does."""
    for attempt in range(WRITE_ATTEMPTS):
        transcript, revision = store_module.read(root, "transcript", transcript_id)
        known = labels(transcript)
        unknown = sorted(set(names) - set(known))
        if unknown:
            raise UnknownSpeaker(
                f"This transcript has no speaker {', '.join(unknown)}; its speakers are "
                f"{', '.join(known) or 'unlabelled'}."
            )
        merged = dict(transcript.speakers)
        for label, name in names.items():
            if name.strip():
                merged[label] = name.strip()
            else:
                merged.pop(label, None)
        try:
            store_module.write(root, "transcript", transcript.model_copy(update={"speakers": merged}),
                               expected_rev=revision)
            return transcript.model_copy(update={"speakers": merged})
        except RevisionConflict:
            if attempt == WRITE_ATTEMPTS - 1:
                raise
    raise AssertionError("unreachable")


def parse_map(pairs: list[str]) -> dict[str, str]:
    """`["SPEAKER_00=a podcast host", ...]` (the CLI's repeated `--map`) -> `{label: name}`."""
    out: dict[str, str] = {}
    for pair in pairs:
        label, sep, name = pair.partition("=")
        if not sep or not label.strip():
            raise ValueError(f"--map wants LABEL=NAME (e.g. SPEAKER_00=\"a podcast host\"), got {pair!r}")
        out[label.strip()] = name.strip().strip('"').strip("'")
    return out


__all__ = ["UnknownSpeaker", "labels", "parse_map", "set_names", "summary"]
