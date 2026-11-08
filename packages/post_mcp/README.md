# post_mcp: the Creative Harness as an MCP server

Lets an LLM agent (Claude Code, Claude Desktop, Codex, any MCP client) edit recorded
interviews by editing their transcripts: read a cut as text, remove or move passages,
make a vertical short, get visual suggestions, and export a DaVinci Resolve timeline.

## Tools

| Tool | What it does |
| --- | --- |
| `get_project` | Recordings, transcripts and cuts, with every id the other tools need. Call first. |
| `read_transcript` | Source transcript as numbered sentences; `include_word_ids` for word-level edits. |
| `read_cut` | A cut as it plays: passages with text, length and word ids, plus its visuals. |
| `create_cut` | A new cut over a whole transcript. Same label twice returns the existing cut. |
| `remove_words` | Cut a run of words (a filler, a false start, a sentence). |
| `restore_words` | Put source words back at a position. |
| `move_words` | Move a run of words (e.g. a sentence) before another word, such as the opening line. |
| `move_passage` | Reorder a whole passage. |
| `undo_edit` | Revert the last edit. |
| `make_short` | A new cut (e.g. 9:16) from word ranges, such as chosen sentences. Same label twice returns the existing short. |
| `suggest_visuals` | Pending B-roll / graphic proposals for the cut or a word range. |
| `accept_visual` | Add one proposal to the cut. |
| `export_timeline` | Write an OpenTimelineIO file for Resolve. |

Every edit returns the updated cut, so an agent doesn't need a follow-up read. Errors are JSON
with a stable `reason`, a `message`, and a `fix` naming the call that resolves it.

Nothing here spends money. Visual suggestions run in a deterministic demo mode unless
`POST3_REAL=1`, in which case they go to the project's configured terminal agent.

## Try it without footage or API keys

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e packages/brandkit -e packages/post_core -e packages/post_mcp
python evals/make_fixture.py /tmp/vlh          # prints a project folder
claude mcp add vlh -- "$(pwd)/.venv/bin/python" -m post_mcp.server
```

Then ask Claude: *"In the project at /tmp/vlh/project, make a 9:16 short of the incident story."*

For Claude Desktop, add to `claude_desktop_config.json`:

```json
{"mcpServers": {"vlh": {"command": "/abs/path/.venv/bin/python", "args": ["-m", "post_mcp.server"]}}}
```

## Agent evals

`evals/run_evals.py` runs five editing tasks with a headless Claude agent that can use only
these tools, then checks the project's final state. See `evals/EVALS.md` for results and what
changed in the tool design because of them.
