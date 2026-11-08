# Agent evals: what broke, what changed

I tested the MCP server the way an agent would use it: a headless Claude Code agent, given only
this server's tools (no shell, no file access), ran editing tasks on a synthetic two-speaker
interview, and a script checked the project's final state. Every step the agent takes is a
tool call, so it can be counted.

**Result:** all tasks completed in both rounds. The revisions cut the calls needed for the
hardest task from 7 to 3, made "move a line" a single undoable edit, fixed a visual count that
misled the agent, and 3 of 3 agents recovered from a deliberately stale id by following the
error's `fix`.

## Tasks

| Id | Task (abridged) | What it tests |
| --- | --- | --- |
| T1 | Remove the fillers and the guest's false start | Word-level edits |
| T2 | Cut the off-topic vacation tangent | Finding content by meaning |
| T3 | Make a 9:16 short of only the incident story, leaving `main` alone | Multi-range selection, not touching the parent |
| T4 | Move the "training did more than any tool" line to the start | Reordering below passage level |
| T5 | Get visual suggestions, accept only the MFA one, export for Resolve | A multi-tool flow end to end |
| T6 | Move passage `<id>` to the end, where the id has gone stale | Error recovery |

## Results

Baseline: 1 run per task. Revised: 3 runs per task. "Edits" counts calls that change a cut.

| Task | Baseline calls / edits | Revised calls / edits | Revised passed |
| --- | --- | --- | --- |
| T1 | 4 / 2 | 4 / 2 | 3 of 3 |
| T2 | 3 / 1 | 3 / 1 | 3 of 3 |
| T3 | **7 / 4** | **3 / 1** | 3 of 3 |
| T4 | **5 / 2** | **3.3 / 1** | 3 of 3 |
| T5 | 4 / 1 | 4 / 1 | 3 of 3 |
| T6 | n/a | 4 / 1, one error each, recovered | 3 of 3 |

Zero tool errors in T1–T5 in either round. Raw results: [`results/`](results/).

## What broke, and what I changed

1. **One accepted visual showed up as two (T5).** The core stores B-roll and its text overlay
   as two layers sharing the same words. The agent accepted one suggestion and `read_cut`
   reported two visuals; `suggest_visuals` never mentioned the overlay, so the agent couldn't
   have known. The agent's model (one suggestion, one visual) was right and the tool's output
   was wrong. **Change:** visuals are grouped per beat with `picture` and `overlay` fields, and
   suggestions say up front whether they carry an overlay.

2. **"Move this line to the top" took two edits (T4).** A new cut is one passage covering the
   whole interview, so `move_passage` had nothing to move. The agent improvised: remove the
   sentence, then restore it at index 0. It worked, but undo then took two steps, and
   `restore_words` needs an index the agent has to work out. **Change:** a `move_words` tool
   (move this word range before that word), wrapping an operation the core already had.
   Every revised run used it, in one edit.

3. **Making a short took 7 calls (T3).** `make_short` took passage ids, but the sentences the
   agent wanted weren't passages yet. It copied the whole cut into a short, then trimmed it
   with three removes. **Change:** `make_short` takes word ranges, e.g. the first and last word
   ids of the chosen sentences, which `read_transcript` already returns. 3 calls, 1 edit.

4. **My checker was wrong (T1).** The baseline scored T1 as a fail; the agent had done exactly
   what was asked, and my check counted a phrase that legitimately appears twice. Fixed and
   re-scored. Reported here because an eval that grades its own tool needs checking too.

## Error recovery (T6)

The task prompt gives a passage id that went stale after an edit, the most common failure
for an agent working from an earlier read. All three runs called `move_passage`, got

```json
{"reason": "unknown_passage_id", "message": "Cut has no passage '…'; ids change after every edit.",
 "fix": "Call read_cut and use a current passage_id."}
```

then called `read_cut`, found the passage by its text, and finished. Recovery rate 3 of 3,
costing one extra call each. The `fix` field is the design choice doing the work: it names
the next call rather than only describing the problem.

## Design rules this produced

- One call to discover every id (`get_project`); the raw CLI's `project show` returned none.
- Return text, not just ids: an agent can't edit what it can't read.
- Accept the ids the agent already holds (word ids), and derive the rest (sync groups,
  camera angles) on the server.
- Match the agent's unit of thought: a sentence, not a passage; one visual, not two layers.
- Every edit returns the new state, so no follow-up read is needed.
- Errors carry a stable `reason` and a `fix` that names the next call.
- Creating something with a label that exists returns it, so a retry can't duplicate it.

## Limits

Small sample (1 baseline and 3 revised runs per task, one model), a synthetic 53-second
transcript, and the deterministic demo suggester rather than a real one. Next: real
interview transcripts, ambiguous requests ("tighten this up"), and a cost-gated generation
tool where the agent has to stop and get a human's approval before spending.

## Reproduce

```bash
pip install -e packages/brandkit -e packages/post_core -e packages/post_mcp
python evals/run_evals.py /tmp/evals --label run --reps 3
```

Needs `ffmpeg` and the Claude Code CLI. Runs use the CLI's own sign-in, not an API key.
