#!/usr/bin/env python3
"""Answer questions from a local Curious Index folder."""

from __future__ import annotations

import argparse
import math
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

TOKEN_RE = re.compile(r"[a-z0-9']+")
TEXT_EXTENSIONS = {".md", ".markdown", ".rst", ".txt"}
DEFAULT_INDEX = Path(__file__).resolve().parent / "index"


@dataclass(frozen=True)
class Chunk:
    path: str
    text: str
    terms: frozenset[str]


def tokenize(text: str) -> frozenset[str]:
    return frozenset(TOKEN_RE.findall(text.lower()))


def split_chunks(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def build_index(root: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        for text in split_chunks(path.read_text(encoding="utf-8", errors="ignore")):
            terms = tokenize(text)
            if terms:
                chunks.append(Chunk(str(path.relative_to(root)), text, terms))
    return chunks


def answer(question: str, chunks: list[Chunk], limit: int = 3) -> str:
    q = tokenize(question)
    if not q:
        return "Ask a question with at least one word."

    # ponytail: simple lexical ranking; add embeddings only when exact words miss too often.
    scored = sorted(
        ((len(q & chunk.terms) / math.sqrt(len(chunk.terms)), chunk) for chunk in chunks),
        key=lambda item: item[0],
        reverse=True,
    )
    matches = [(score, chunk) for score, chunk in scored if score > 0][:limit]
    if not matches:
        return "I don't know from the index."

    lines = ["Answer from the index:"]
    for n, (_, chunk) in enumerate(matches, 1):
        snippet = " ".join(chunk.text.split())
        lines.append(f"{n}. {snippet}\n   source: {chunk.path}")
    return "\n".join(lines)


def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "index"
        root.mkdir()
        (root / "plants.md").write_text(
            "Tomatoes need full sun.\n\nMushrooms grow in shade.", encoding="utf-8"
        )
        chunks = build_index(root)
        assert "Tomatoes need full sun" in answer("what needs sun?", chunks)
        assert "source: plants.md" in answer("what needs sun?", chunks)
        assert answer("quantum mechanics", chunks) == "I don't know from the index."
    print("self-test ok")


def main() -> int:
    parser = argparse.ArgumentParser(description="Answer questions from local index files.")
    parser.add_argument("question", nargs="*", help="question to answer")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX, help="folder containing .md/.txt/.rst files")
    parser.add_argument("--limit", type=int, default=3, help="max cited snippets")
    parser.add_argument("--self-test", action="store_true", help="run the built-in check")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    root = args.index
    if not root.exists():
        sys.exit(f"Index not found: {root}. Put .md/.txt/.rst files there or pass --index.")

    chunks = build_index(root)
    if not chunks:
        sys.exit(f"No .md/.txt/.rst files found under {root}.")

    print(answer(" ".join(args.question), chunks, args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
