# Terminal agents (T36)

Three operations need judgement, not a generator, so Post3 hands them to a terminal agent on
your own subscription: Claude Code (`claude -p`) or the Codex CLI (`codex exec`). They do not
use an API key or an SDK, and they never bill API dollars. The adapter is
`packages/post_core/post_core/agents/` (`ask_json`). It is a port of the old flow's
`~/.claude/skills/post/scripts/terminal_agent.py`.

## What runs where

| Operation | Started by | Runs in | The agent gets | What comes back, and where it goes |
|---|---|---|---|---|
| `suggest_visuals` | "Suggest visuals" in the editor (`POST /api/projects/{pid}/cuts/{cut_id}/suggested-visuals`) | the API process, inside the request | the project kit's writer context, the cast names, the cut's own words grouped by section (speaker and length per sentence, cut words left out), the neighbouring beats, the editorial rules and the beat taxonomy | `{"proposals": [...]}`. Each proposal is validated and stored as a pending suggestion, shown dashed with accept/dismiss. It never becomes a span until a human accepts it, and it is dropped if it overlaps a placed beat on the same layer. |
| `brief_write` | the `brief.write` node (motion-graphic recipe) | a queue worker (`design` lane) | the words spoken over the beat, the editor's direction, the instruction and the writer context (the node's own, else the project kit's) | `{"brief": "..."}`, written to `brief.txt` |
| `motion_from_frame` | the `motion.from_frame` node, once a start frame is picked | a queue worker (`design` lane) | the picked frame (as an image), the beat's motion and static hints, the kit's writer context and the house's forbidden motion terms | `{"subject_motion", "static"}`. These go through `brandkit` `motion_prompt`, which keeps the beat's own camera and pacing and runs the purity check, and the result is written to `motion_prompt.txt`. Brand-impure text fails the node. |

The prompts live in `post_core/edit/suggest_prompt.py` and `post_core/recipes/agent_prompts.py`.
`tests/edit/snapshots/suggest_prompt_selection.txt` is a full example of the Suggest-visuals
prompt. Regenerate it with `UPDATE_SNAPSHOTS=1 pytest tests/edit/test_suggest_agent.py`.

**Fake mode makes no agent call.** With `POST3_FAKE_PROVIDERS=1` (the `make dev` default),
Suggest visuals uses the deterministic demo suggester, `brief.write` composes a placeholder,
and `motion.from_frame` uses the hints as written. Anything else is real mode
(`POST3_REAL=1 make dev`, or a CLI or API run without the variable). Agent calls cost
subscription usage, not credits, so the T31 spend gate does not cover them.

## Switching provider or model

Put `<project>/.post3/agents.json` in place. Every key is optional:

```json
{
  "default":           {"provider": "claude", "model": null, "timeout_seconds": 420},
  "suggest_visuals":   {"provider": "codex", "model": "gpt-5-codex"},
  "motion_from_frame": {"model": "sonnet"}
}
```

- An operation's entry is laid over `default`, and `default` is laid over the built-ins
  (`claude`, the CLI's own default model, 420 s).
- `provider` must be `claude` or `codex`. A `model` value is passed through as `--model`
  exactly as written.
- Unknown keys or fields are refused with a clear error, so a typo cannot silently fall back
  to the default.
- There is never a fallback from one provider to the other. A missing, failing or
  rate-limited CLI fails the call and gives the reason.
- The binary comes from `PATH` (`claude`, `codex`). Set `POST3_CLAUDE_BIN` or
  `POST3_CODEX_BIN` to use a specific executable, for example when the API server's PATH
  differs from your shell's.

Sign in to the CLI you choose once in a terminal (`claude`, or `codex login`) before the first
real run.

## What the agent can read and do

- **Read only, nothing else.** Claude runs with no tools (`--tools ""`). When an image is
  attached, it gets only `Read`, limited (`--add-dir`) to that image's folder.
  `--permission-mode dontAsk`, so it cannot ask for more. Codex runs in its `read-only`
  sandbox and gets images through `--image`.
- **No MCP servers.** For Claude: `--strict-mcp-config` with an empty config. For Codex:
  `-c mcp_servers={}`.
- **No saved session.** For Claude: `--no-session-persistence`. For Codex: `--ephemeral`.
- **Runs in an empty temp directory.** The project is not the working directory. Everything
  the agent needs is in the prompt (stdin) or in an attached image. Codex's read-only sandbox
  can still read other files on disk; Claude with no tools cannot. User-level CLI settings
  (for example `~/.claude/CLAUDE.md`) may still apply.
- **No API keys.** `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `OPENAI_API_KEY` and
  `CODEX_API_KEY` are removed from the agent's environment, so it can only run on the
  signed-in subscription.
- **Only the final message counts.** For Claude that is stdout. For Codex it is
  `--output-last-message`; tool events are never a result. The reply must be one JSON object.
  A ```` ```json ```` fence is tolerated, but prose around the object is not. Nothing is
  written until the reply has been validated.
- **Timeouts and cancellation stop the agent.** On a timeout, or when a cancelled worker gets
  SIGTERM, the agent's whole process group is stopped.

## When it fails

Every failure is an `AgentError` with a `reason`. Workers exit 1 with
`result{ok: false, detail, reason}`. The API answers `502 {"error", "reason"}`, and the
editor shows the sentence next to the Suggest button while pending proposals stay as they were.

| reason | meaning |
|---|---|
| `not_found` | the CLI is not on PATH, or not at `POST3_*_BIN` |
| `timeout` | no answer within `timeout_seconds`; the agent was stopped |
| `failed` | the CLI exited non-zero (for example a usage limit); its stderr tail is in the message |
| `bad_json` | the final message was not one JSON object of the expected shape |
| `config` | `.post3/agents.json` is invalid |

## Tests

Tests never run a real agent. The post_core and post_api suites point `POST3_CLAUDE_BIN` and
`POST3_CODEX_BIN` at a path that does not exist, so a forgotten real-mode call fails with
`not_found`. Adapter tests install a fake agent script as `claude` and `codex` on a temp PATH
(`fake_agent` in `packages/post_core/tests/conftest.py`). The script records argv and the
stdin prompt, then echoes a canned reply, sleeps, fails, or emits garbage.

## Unverified

- No real `claude` or `codex` call has been made through this adapter. The flags match the
  old flow's production adapter, except Codex's `-c mcp_servers={}`, which has never been run.
- The quality of real Suggest-visuals proposals, briefs and motion slots has not been checked.
  T18 runs the agent on a real slice.
- Suggest visuals runs inside the API request. A long run holds that request open for up to
  `timeout_seconds`.
