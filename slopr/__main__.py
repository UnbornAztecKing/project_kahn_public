"""CLI entry point — ``python -m slopr``."""

from __future__ import annotations

from pathlib import Path

import click


@click.command()
@click.argument("jsonl_file", type=click.Path(exists=True, path_type=Path))
@click.option("--turn", type=int, default=None, help="Jump to turn N on startup.")
@click.option("--compact", is_flag=True, help="Compact card display.")
@click.option(
    "--split-width",
    type=int,
    default=100,
    show_default=True,
    help="Min content pane width (columns) for side-by-side A/B layout. 0 disables.",
)
@click.option(
    "--double-newlines/--no-double-newlines",
    default=True,
    show_default=True,
    help="Double newlines in prose text values for visual structure.",
)
@click.option(
    "--wrap-indent",
    type=int,
    default=0,
    show_default=True,
    help="Indent continuation lines in prose text values by N spaces.",
)
@click.option(
    "--manifest",
    type=click.Path(path_type=Path),
    default=None,
    help=(
        "Path to a branch manifest file (e.g. sim.jsonl.branches). "
        "If omitted, the conventional path {jsonl_file}.branches is used "
        "(auto-created on first branch). "
        "Pass --no-manifest to disable branch support entirely."
    ),
)
@click.option(
    "--no-manifest",
    "disable_manifest",
    is_flag=True,
    default=False,
    help="Disable branch support even if a manifest file exists.",
)
@click.option(
    "--analysis-model",
    default="claude-sonnet-4-6",
    show_default=True,
    help="Anthropic model ID used for right-click AI analysis commands.",
)
def main(
    jsonl_file: Path,
    turn: int | None,
    compact: bool,
    split_width: int,
    double_newlines: bool,
    wrap_indent: int,
    manifest: Path | None,
    disable_manifest: bool,
    analysis_model: str,
) -> None:
    """Launch the wargame TUI viewer for a JSONL event file."""
    from slopr.app import WargameApp
    from slopr.branches import BranchStore
    from slopr.sim_queue import SimQueue
    from slopr.store import JSONLEventStore

    store = JSONLEventStore(jsonl_file)

    branch_store: BranchStore | None = None
    if not disable_manifest:
        manifest_path = manifest or BranchStore.manifest_path_for(jsonl_file)
        if manifest_path.exists():
            branch_store = BranchStore(manifest_path)
        else:
            # Auto-create the manifest so branching works on first double-click
            branch_store = BranchStore.init(jsonl_file)

    sim_queue = SimQueue(SimQueue.path_for(jsonl_file))

    app = WargameApp(
        store=store,
        source_path=jsonl_file,
        start_turn=turn,
        split_threshold=split_width,
        double_newlines=double_newlines,
        wrap_indent=wrap_indent,
        branch_store=branch_store,
        sim_queue=sim_queue,
        analysis_model=analysis_model,
    )
    app.run()


if __name__ == "__main__":
    main()
