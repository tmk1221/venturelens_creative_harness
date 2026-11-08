"""T35: the one way a new transcript lands in a project -- written atomically (the store's
temp-file-then-rename under a lock), then linked to its shoot. Every path uses it: a Deepgram
job, `post ingest import-transcript`, the Ingest page's import, `post project new`.

A new transcript for a sync group that already had one keeps the speaker names given to the
group's latest transcript (`Transcript.speakers`), for every label it still uses -- so
re-importing or re-transcribing never throws away "SPEAKER_00 is a podcast host".
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ...model.shoot import Shoot
from ...model.transcript import Transcript
from ...store import store as store_module
from ...store.errors import NotFound, RevisionConflict

LINK_ATTEMPTS = 5


def latest_for_group(root: str | Path, shoot: Shoot, sync_group_id: str) -> Optional[Transcript]:
    """The group's most recently linked transcript (`shoot.transcript_ids` is in link order)."""
    for transcript_id in reversed(shoot.transcript_ids):
        try:
            transcript, _rev = store_module.read(root, "transcript", transcript_id)
        except NotFound:
            continue
        if transcript.sync_group_id == sync_group_id:
            return transcript
    return None


def inherit_speaker_names(previous: Optional[Transcript], transcript: Transcript) -> Transcript:
    if previous is None or not previous.speakers:
        return transcript
    labels = {w.speaker for w in transcript.words if w.speaker}
    names = {label: name for label, name in previous.speakers.items() if label in labels}
    return transcript.model_copy(update={"speakers": {**names, **transcript.speakers}})


def add_transcript(root: str | Path, shoot_id: str, transcript: Transcript) -> Transcript:
    """Write `transcript` as a new store object and append it to the shoot's transcripts.
    Returns what was written (with any inherited speaker names)."""
    shoot, _rev = store_module.read(root, "shoot", shoot_id)
    transcript = inherit_speaker_names(latest_for_group(root, shoot, transcript.sync_group_id), transcript)
    store_module.write(root, "transcript", transcript, expected_rev=0)
    for attempt in range(LINK_ATTEMPTS):
        shoot, revision = store_module.read(root, "shoot", shoot_id)
        updated = shoot.model_copy(update={"transcript_ids": [*shoot.transcript_ids, transcript.id]})
        try:
            store_module.write(root, "shoot", updated, expected_rev=revision)
            return transcript
        except RevisionConflict:
            # Another writer touched the shoot (e.g. a peaks path): re-read and retry.
            if attempt == LINK_ATTEMPTS - 1:
                raise
    return transcript


__all__ = ["add_transcript", "inherit_speaker_names", "latest_for_group"]
