"""`post`: argparse wiring + dispatch. Every command prints one JSON object (see
`output.run_command`); this module only builds the parser and picks which command function
to call -- all the actual work lives in `commands/*.py`.
"""
from __future__ import annotations

import argparse
import sys
from typing import Callable

from . import config as config_mod
from .commands import cut as cut_cmds
from .commands import export as export_cmds
from .commands import ingest as ingest_cmds
from .commands import project as project_cmds
from .commands import queue as queue_cmds
from .commands import workflow as workflow_cmds
from .output import run_command

Handler = Callable[[argparse.Namespace], object]


def _root_option(parser: argparse.ArgumentParser, *, required_positional: bool = False) -> None:
    if required_positional:
        parser.add_argument("root", help="project root directory")
    else:
        parser.add_argument("--root", default=None, help="project root (default: cwd)")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="post")
    ap.add_argument("--pretty", action="store_true", help="pretty-print JSON output")
    sub = ap.add_subparsers(dest="command", required=True)

    handlers: dict[str, Handler] = {}

    def add(name: str, handler: Handler, *, aliases: tuple[str, ...] = ()) -> argparse.ArgumentParser:
        p = sub.add_parser(name)
        handlers[name] = handler
        for alias in aliases:
            handlers[alias] = handler
        return p

    p = add("init", project_cmds.init)
    _root_option(p, required_positional=True)
    p.add_argument("--name", default=None)

    project_sub = add("project", None).add_subparsers(dest="project_command", required=True)
    p = project_sub.add_parser("new", help="T34/T39: a project from local recordings, in one idempotent call")
    p.add_argument("name", nargs="?", default=None, help="the project name (or --project)")
    p.add_argument("--project", default=None, help="T39: the project name = the Resolve project name")
    p.add_argument("--company", default=None, help="T39: make it <library>/<company>/<project>/ in the media library")
    p.add_argument("--root", default=None, help="the project folder, without --company (never a footage folder)")
    p.add_argument("--source", required=True, action="append", dest="sources", help="a recording; repeat for more")
    p.add_argument("--copy", action="store_true", help="T39: copy recordings outside the project into Video/source")
    p.add_argument("--transcript", action="append", dest="transcripts", help="a transcript file per --source, in order")
    p.add_argument("--kit", default=None, help="a brand kit id (the company's brand/, or packages/brandkit/kits/)")
    handlers["project.new"] = project_cmds.project_new
    p = project_sub.add_parser("show")
    _root_option(p)
    handlers["project.show"] = project_cmds.project_show
    p = project_sub.add_parser("set-kit")
    _root_option(p)
    p.add_argument("kit_id", help="the company's kit (its name) or a kit folder under packages/brandkit/kits/")
    handlers["project.set-kit"] = project_cmds.project_set_kit
    p = project_sub.add_parser("set", help="T42: project settings")
    _root_option(p)
    p.add_argument("--picture-mode", dest="picture_mode", choices=("presenter", "audio_only"), default=None,
                   help="presenter: someone on camera; audio_only: a voice, every second needs a picture")
    handlers["project.set"] = project_cmds.project_set

    source_sub = add("source", None).add_subparsers(dest="source_command", required=True)
    p = source_sub.add_parser("add")
    _root_option(p)
    p.add_argument("--path", required=True)
    p.add_argument("--shoot", default=None)
    p.add_argument("--role", default="other")
    handlers["source.add"] = project_cmds.source_add
    p = source_sub.add_parser("probe")
    _root_option(p)
    p.add_argument("--path", required=True)
    handlers["source.probe"] = project_cmds.source_probe

    ingest_sub = add("ingest", None).add_subparsers(dest="ingest_command", required=True)
    p = ingest_sub.add_parser("proxy")
    _root_option(p)
    p.add_argument("--shoot", required=True)
    p.add_argument("--source-id", required=True, dest="source_id")
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--force", action="store_true")
    p.add_argument("--start", type=float, default=None, help="partial proxy: start offset in seconds")
    p.add_argument("--duration", type=float, default=None, help="partial proxy: duration in seconds")
    handlers["ingest.proxy"] = ingest_cmds.ingest_proxy
    p = ingest_sub.add_parser("audio")
    _root_option(p)
    p.add_argument("--shoot", required=True)
    p.add_argument("--source-id", required=True, dest="source_id")
    p.add_argument("--force", action="store_true")
    handlers["ingest.audio"] = ingest_cmds.ingest_audio
    p = ingest_sub.add_parser("peaks")
    _root_option(p)
    p.add_argument("--shoot", required=True)
    p.add_argument("--source-id", required=True, dest="source_id")
    p.add_argument("--rate", type=int, default=100)
    handlers["ingest.peaks"] = ingest_cmds.ingest_peaks
    p = ingest_sub.add_parser("transcribe", help="T35: a paid, queued transcription of a recording's audio proxy")
    _root_option(p)
    p.add_argument("--shoot", default=None)
    p.add_argument("--source-id", default=None, dest="source_id")
    p.add_argument("--sync-group", default=None, dest="sync_group", help="instead of --shoot/--source-id")
    p.add_argument("--provider", default="deepgram", help="deepgram (paid); 'local' is not built yet")
    p.add_argument("--estimate", action="store_true", help="only print what it would cost")
    p.add_argument("--budget", default=None, help="an existing usd budget (`post budget set`) that pays for it")
    p.add_argument("--by", default=None)
    handlers["ingest.transcribe"] = ingest_cmds.ingest_transcribe
    p = ingest_sub.add_parser("import-transcript")
    _root_option(p)
    p.add_argument("--shoot", required=True)
    p.add_argument("--sync-group", required=True, dest="sync_group")
    p.add_argument("--path", required=True)
    p.add_argument("--format", default=None)
    p.add_argument("--fingerprint", default=None)
    handlers["ingest.import-transcript"] = ingest_cmds.ingest_import_transcript

    transcript_sub = add("transcript", None).add_subparsers(dest="transcript_command", required=True)
    p = transcript_sub.add_parser("speakers", help="T35: list speakers, or name them with --map")
    _root_option(p)
    p.add_argument("transcript_id")
    p.add_argument("--map", action="append", default=[], help='LABEL=NAME, e.g. SPEAKER_00="a podcast host"; repeat')
    handlers["transcript.speakers"] = ingest_cmds.transcript_speakers

    cut_sub = add("cut", None).add_subparsers(dest="cut_command", required=True)
    p = cut_sub.add_parser("new")
    _root_option(p)
    p.add_argument("--transcript", required=True)
    p.add_argument("--angle", required=True, help="angle Source id")
    p.add_argument("--aspect", default="16:9")
    p.add_argument("--variant-label", default=None, dest="variant_label")
    handlers["cut.new"] = cut_cmds.cut_new
    p = cut_sub.add_parser("show")
    _root_option(p)
    p.add_argument("--cut", required=True)
    handlers["cut.show"] = cut_cmds.cut_show
    p = cut_sub.add_parser("op")
    _root_option(p)
    p.add_argument("name")
    p.add_argument("--cut", required=True)
    p.add_argument("--args", default=None, dest="op_args", help="JSON object of op kwargs")
    handlers["cut.op"] = cut_cmds.cut_op
    p = cut_sub.add_parser("undo")
    _root_option(p)
    p.add_argument("--cut", required=True)
    handlers["cut.undo"] = cut_cmds.cut_undo
    p = cut_sub.add_parser("redo")
    _root_option(p)
    p.add_argument("--cut", required=True)
    handlers["cut.redo"] = cut_cmds.cut_redo
    p = cut_sub.add_parser("derive")
    _root_option(p)
    p.add_argument("--parent", required=True)
    p.add_argument("--passage-ids", required=True, dest="passage_ids", help="JSON array")
    p.add_argument("--aspect", default="16:9")
    p.add_argument("--variant-label", default=None, dest="variant_label")
    handlers["cut.derive"] = cut_cmds.cut_derive

    workflow_sub = add("workflow", None).add_subparsers(dest="workflow_command", required=True)
    p = workflow_sub.add_parser("new")
    _root_option(p)
    p.add_argument("--recipe", required=True)
    p.add_argument("--graph", default=None, help="JSON file: {nodes: [...], edges: [...]}")
    handlers["workflow.new"] = workflow_cmds.workflow_new
    p = workflow_sub.add_parser("show")
    _root_option(p)
    p.add_argument("--workflow", required=True)
    handlers["workflow.show"] = workflow_cmds.workflow_show
    p = workflow_sub.add_parser("plan")
    _root_option(p)
    p.add_argument("--workflow", required=True)
    p.add_argument("--targets", default=None, help="JSON array of node ids")
    p.add_argument("--from", default=None, dest="from_node")
    handlers["workflow.plan"] = workflow_cmds.workflow_plan
    p = workflow_sub.add_parser("states")
    _root_option(p)
    p.add_argument("--workflow", required=True)
    handlers["workflow.states"] = workflow_cmds.workflow_states

    p = add("run", queue_cmds.run)
    _root_option(p)
    p.add_argument("--workflow", required=True)
    p.add_argument("--from", default=None, dest="from_node")
    p.add_argument("--targets", default=None, help="JSON array of node ids")
    p.add_argument("--budget", default=None,
                   help="an existing budget (`post budget set`) to authorise spending nodes against")
    p.add_argument("--by", default=None)
    p.add_argument("--node-ids", default=None, dest="node_ids",
                   help="JSON array: limit the authorisation to these spending node ids")
    p.add_argument("--covers-downstream", action="store_true", dest="covers_downstream")

    queue_sub = add("queue", None).add_subparsers(dest="queue_command", required=True)
    p = queue_sub.add_parser("list")
    _root_option(p)
    p.add_argument("--workflow", default=None)
    p.add_argument("--state", default=None)
    handlers["queue.list"] = queue_cmds.queue_list
    p = queue_sub.add_parser("show")
    _root_option(p)
    p.add_argument("job")
    handlers["queue.show"] = queue_cmds.queue_show
    p = queue_sub.add_parser("cancel")
    _root_option(p)
    p.add_argument("job")
    handlers["queue.cancel"] = queue_cmds.queue_cancel
    p = queue_sub.add_parser("serve")
    _root_option(p)
    p.add_argument("--workflow", required=True)
    p.add_argument("--once", action="store_true", help="drain the queue then exit, instead of serving forever")
    handlers["queue.serve"] = queue_cmds.queue_serve

    p = add("approve", queue_cmds.approve)
    _root_option(p)
    p.add_argument("content_hash")
    p.add_argument("--by", default=None)

    p = add("revoke", queue_cmds.revoke)
    _root_option(p)
    p.add_argument("content_hash")

    budget_sub = add("budget", None).add_subparsers(dest="budget_command", required=True)
    p = budget_sub.add_parser("set")
    _root_option(p)
    p.add_argument("--id", required=True)
    p.add_argument("--cap", type=float, required=True)
    p.add_argument("--unit", required=True, help="the provider's unit: credits (Higgsfield), usd (Deepgram)")
    handlers["budget.set"] = queue_cmds.budget_set
    p = budget_sub.add_parser("show")
    _root_option(p)
    p.add_argument("--id", required=True)
    handlers["budget.show"] = queue_cmds.budget_show

    export_sub = add("export", None).add_subparsers(dest="export_command", required=True)
    p = export_sub.add_parser("otio")
    _root_option(p)
    p.add_argument("cut")
    p.add_argument("--version", type=int, default=None)
    p.add_argument("--patch-since", type=int, default=None, dest="patch_since")
    handlers["export.otio"] = export_cmds.export_otio

    p = add("doctor", queue_cmds.doctor)
    _root_option(p)

    ap._post3_handlers = handlers  # type: ignore[attr-defined]  # stashed for dispatch()
    return ap


def _dispatch_key(args: argparse.Namespace) -> str:
    for group in ("project_command", "source_command", "ingest_command", "transcript_command", "cut_command",
                   "workflow_command", "queue_command", "budget_command", "export_command"):
        sub = getattr(args, group, None)
        if sub is not None:
            return f"{args.command}.{sub}"
    return args.command


def main(argv: list[str] | None = None) -> int:
    config_mod.load_env()
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers: dict[str, Handler] = parser._post3_handlers  # type: ignore[attr-defined]
    key = _dispatch_key(args)
    handler = handlers.get(key)
    if handler is None:
        parser.error(f"no handler for {key!r}")
        return 2
    return run_command(lambda: handler(args), pretty=args.pretty)


if __name__ == "__main__":
    sys.exit(main())
