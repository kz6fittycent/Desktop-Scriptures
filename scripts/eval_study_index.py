"""Benchmark a built study index (see src/scriptures/study_index.py)
against scripts/study_index_eval_questions.json, using the same
embeddings endpoint and model the index was built with.

    python3 scripts/eval_study_index.py INDEX_DB EMBEDDINGS_URL MODEL [--api-key KEY] [-v]

e.g., for a source checkout's index built through a local Ollama:

    python3 scripts/eval_study_index.py data/study_index.db \\
        http://localhost:11434/v1 embeddinggemma

Reports, over all questions:

- hit@5 / hit@10: share of questions with at least one listed passage
  in the top 5 / top 10 results (mixed - talks, topics, and so on
  included, since that's what a user sees);
- MRR@10: mean reciprocal rank of the first listed passage (1.0 = always
  first, 0.5 = typically second, 0 = never in the top 10);
- the same three restricted to scripture pieces only;
- duplicate slots: top-10 results repeating the same book/chapter/verses
  as a higher result (the Bible and the JST share numbering and most
  wording).

Scores are only meaningful relative to each other - run before and after
a change. The question list isn't exhaustive, so a "miss" may still have
returned other good passages; -v shows what came back.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures import study_index as si  # noqa: E402

QUESTIONS_PATH = PROJECT_ROOT / "scripts" / "study_index_eval_questions.json"
_REF_RE = re.compile(r"^(?P<book>.+?)\s+(?P<chapter>\d+)(?::(?P<start>\d+)(?:-(?P<end>\d+))?)?$")


def parse_range(reference: str) -> tuple[str, int, int | None, int | None] | None:
    match = _REF_RE.match(reference.strip())
    if not match:
        return None
    start = int(match["start"]) if match["start"] else None
    end = int(match["end"]) if match["end"] else start
    return match["book"], int(match["chapter"]), start, end


def covers(range_ref: str, wanted: str) -> bool:
    have, want = parse_range(range_ref), parse_range(wanted)
    if have is None or want is None or have[:2] != want[:2]:
        return False
    if have[2] is None:  # a whole chapter covers any verse in it
        return True
    return have[2] <= want[2] <= have[3]


def is_relevant(hit: si.SearchHit, wanted: list[str]) -> bool:
    candidates = [hit.meta.get("reference"), hit.meta.get("related_reference")]
    return any(c and covers(c, w) for c in candidates for w in wanted)


def embed(url: str, api_key: str, model: str, text: str) -> list[float]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        url.rstrip("/") + "/embeddings",
        data=json.dumps({"model": model, "input": [text]}).encode(),
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())["data"][0]["embedding"]


def format_query(model: str, question: str) -> str:
    # Uses the index's own per-model query formatting when this version
    # of study_index.py has one.
    formatter = getattr(si, "format_query", None)
    return formatter(model, question) if formatter else question


def score(rank_lists: list[list[int]]) -> tuple[float, float, float]:
    n = len(rank_lists)
    hit5 = sum(1 for ranks in rank_lists if ranks and ranks[0] <= 5) / n
    hit10 = sum(1 for ranks in rank_lists if ranks) / n
    mrr = sum(1 / ranks[0] for ranks in rank_lists if ranks) / n
    return hit5, hit10, mrr


def duplicate_slots(hits: list[si.SearchHit]) -> int:
    seen: set[tuple] = set()
    duplicates = 0
    for hit in hits:
        if hit.kind != "scripture":
            continue
        key = (hit.meta.get("book"), hit.meta.get("chapter"), hit.meta.get("verse_start"),
               hit.meta.get("verse_end"))
        duplicates += key in seen
        seen.add(key)
    return duplicates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("index_db")
    parser.add_argument("embeddings_url")
    parser.add_argument("model")
    parser.add_argument("--api-key", default="")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    conn = sqlite3.connect(f"file:{args.index_db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    index = si.StudyIndex(conn)
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))["questions"]

    mixed_ranks, scripture_ranks, dupes = [], [], 0
    for item in questions:
        vector = embed(args.embeddings_url, args.api_key, args.model, format_query(args.model, item["q"]))
        mixed = index.search(item["q"], vector, limit=10)
        scripture = index.search(item["q"], vector, kinds={"scripture"}, limit=10)
        mixed_ranks.append([i for i, h in enumerate(mixed, 1) if is_relevant(h, item["refs"])])
        scripture_ranks.append([i for i, h in enumerate(scripture, 1) if is_relevant(h, item["refs"])])
        dupes += duplicate_slots(mixed)
        if args.verbose:
            print(f"\nQ: {item['q']}  -> relevant at {mixed_ranks[-1] or 'none'}")
            for i, h in enumerate(mixed[:5], 1):
                label = h.meta.get("reference") or h.meta.get("title") or h.meta.get("name") or h.key
                mark = "*" if is_relevant(h, item["refs"]) else " "
                print(f"   {mark}{i}. [{h.kind}] {label[:90]}")

    m5, m10, mmrr = score(mixed_ranks)
    s5, s10, smrr = score(scripture_ranks)
    print(f"\n{len(questions)} questions, model {args.model}")
    print(f"  mixed:          hit@5 {m5:.0%}  hit@10 {m10:.0%}  MRR@10 {mmrr:.3f}")
    print(f"  scripture only: hit@5 {s5:.0%}  hit@10 {s10:.0%}  MRR@10 {smrr:.3f}")
    print(f"  duplicate slots in mixed top 10: {dupes} of {10 * len(questions)}")


if __name__ == "__main__":
    main()
