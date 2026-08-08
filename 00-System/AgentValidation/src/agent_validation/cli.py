from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .candidate_selector import NoCandidatesFound, RankedCandidate, select_candidates
from .manifest_loader import ManifestError, load_manifest

CONFIG_FILENAME = "aihub.json"
DEFAULT_MANIFEST_RELATIVE_PATH = Path("02-Curated") / "Metadata" / "document_normalizer_manifest.jsonl"
DEFAULT_MARKDOWN_ROOT_RELATIVE_PATH = Path("02-Curated") / "Markdown"

SHA256_SHORT_LENGTH = 12


class RootNotFoundError(RuntimeError):
    pass


def find_repo_root(start: Path | None = None) -> Path:
    """Mirrors knowledge_compiler.config.find_repo_root's walk-up-to-aihub.json
    pattern. Deliberately duplicated rather than imported -- AgentValidation
    stays fully decoupled from the knowledge_compiler package."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / CONFIG_FILENAME).is_file():
            return candidate
    raise RootNotFoundError(f"'{CONFIG_FILENAME}' not found in '{current}' or any parent directory")


def _format_bundle(question: str, candidates: list[RankedCandidate], markdown_root: Path) -> str:
    lines: list[str] = []
    lines.append("=== AGENT VALIDATION CONTEXT BUNDLE ===")
    lines.append("")
    lines.append(f"Question: {question}")
    lines.append("")
    lines.append(f"Candidates: {len(candidates)}")

    for index, candidate in enumerate(candidates, start=1):
        entry = candidate.entry
        lines.append("")
        lines.append(f"--- [{index}] ---")
        lines.append(f"document_id: {entry.document_id}")
        lines.append(f"source_relative_path: {entry.relative_path}")
        lines.append(f"knowledge_source: {entry.knowledge_source}")
        lines.append(f"document_type: {entry.document_type}")
        lines.append(f"language: {entry.language}")
        lines.append(f"source_sha256: {entry.source_sha256[:SHA256_SHORT_LENGTH]}")
        lines.append(f"converter_version: {entry.converter_version}")
        lines.append(f"output_relative_path: {entry.output_relative_path}")
        lines.append(f"matched_tokens ({candidate.score}): {', '.join(candidate.matched_tokens)}")
        lines.append("")
        lines.append("Content:")
        markdown_path = markdown_root / entry.output_relative_path
        try:
            content = markdown_path.read_text(encoding="utf-8")
        except OSError as exc:
            content = f"[unable to read output_relative_path: {exc}]"
        lines.append(content)

    lines.append("")
    lines.append("=== INSTRUCTIONS ===")
    lines.append(
        "Answer the question ONLY using the numbered sources above. Cite every "
        "claim inline with the matching bracketed number, e.g. [1], [2]. If the "
        "sources do not contain the answer, say so explicitly instead of guessing."
    )
    return "\n".join(lines)


def ask(question: str, *, manifest_path: Path, markdown_root: Path) -> str:
    entries = load_manifest(manifest_path)
    result = select_candidates(question, entries, markdown_root=markdown_root)

    if isinstance(result, NoCandidatesFound):
        return (
            "=== AGENT VALIDATION CONTEXT BUNDLE ===\n\n"
            f"Question: {question}\n\n"
            f"No candidates found: {result.reason}\n"
            "No sources are available -- do not answer from prior knowledge; "
            "report that the corpus does not contain relevant information."
        )

    return _format_bundle(question, result, markdown_root)


def _add_path_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Path inside the AI Hub repository, used only to resolve --manifest/"
        "--markdown-root defaults (defaults to the current directory).",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Path to the curated document-normalizer manifest JSONL "
        "(defaults to <root>/02-Curated/Metadata/document_normalizer_manifest.jsonl).",
    )
    parser.add_argument(
        "--markdown-root",
        type=Path,
        default=None,
        help="Root directory that output_relative_path values resolve against "
        "(defaults to <root>/02-Curated/Markdown).",
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m agent_validation",
        description=(
            "AI Hub Agent Validation harness -- deterministic, explainable "
            "candidate selection over the curated Knowledge Compiler manifest. "
            "No embeddings, no vector DB, no LLM calls in this tool itself."
        ),
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    ask_parser = subparsers.add_parser("ask", help="Ask a question and print a context bundle.")
    # --root/--manifest/--markdown-root are registered on the "ask"
    # subparser only (not the top-level parser): argparse resets a
    # subparser's own argument defaults after the subcommand token, so
    # registering the same options on both would silently clobber a value
    # given before "ask" back to None.
    _add_path_arguments(ask_parser)
    ask_parser.add_argument("question", help="The question text.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    manifest_path = args.manifest
    markdown_root = args.markdown_root

    if manifest_path is None or markdown_root is None:
        try:
            root = find_repo_root(args.root)
        except RootNotFoundError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if manifest_path is None:
            manifest_path = root / DEFAULT_MANIFEST_RELATIVE_PATH
        if markdown_root is None:
            markdown_root = root / DEFAULT_MARKDOWN_ROOT_RELATIVE_PATH

    if args.command == "ask":
        try:
            output = ask(args.question, manifest_path=manifest_path, markdown_root=markdown_root)
        except ManifestError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(output)
        return 0

    parser.error(f"unknown command '{args.command}'")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
