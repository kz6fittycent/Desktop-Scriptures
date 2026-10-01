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
A question's listed answers may also be Strong's numbers ("H4899"), met
by that lexicon entry - see study_index_lexicon_questions.json.

- MRR@10: mean reciprocal rank of the first listed passage (1.0 = always
  first, 0.5 = typically second, 0 = never in the top 10);
  (with the same per-kind caps AI search uses);
- the same three restricted to scripture pieces only;
- duplicate slots: top-10 results repeating the same book/chapter/verses
  as a higher result (the Bible and the JST share numbering and most
  wording).

With --select CHAT_URL CHAT_MODEL, also scores the full AI-search
pipeline (src/scriptures/study_ask.py): the index's candidates, narrowed
and reordered by that chat model - "selected" below - falling back to the
index's own order when the model's reply isn't usable, as the app does.

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
    # A Strong's number ("H4899") is answered by that lexicon entry.
    if hit.kind == "lexicon":
        return hit.meta.get("strongs") in wanted
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


def si_kind_limits() -> dict | None:
    # The same per-kind caps AI search uses, when this version has them.
    return getattr(si, "MIXED_KIND_LIMITS", None)


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


def chat(chat_url: str, chat_model: str, messages: list[dict], temperature: float) -> str:
    request = urllib.request.Request(
        chat_url.rstrip("/") + "/chat/completions",
        data=json.dumps({"model": chat_model, "temperature": temperature, "messages": messages}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read())["choices"][0]["message"]["content"]


# The main database, for Topical Guide key passages (see main()).
SCRIPTURES_CONN = None


def select(chat_url: str, chat_model: str, question: str, vector, index) -> tuple[list, bool]:
    """The app's AI-search pipeline, synchronously: candidates, then the
    chat model's choice (see study_ask.py)."""
    from scriptures import study_ask

    topic_ids = None
    if SCRIPTURES_CONN is not None:
        topics = study_ask.all_topics(SCRIPTURES_CONN)
        try:
            content = chat(chat_url, chat_model, study_ask.topic_messages([question], topics), 0)
            topic_ids = study_ask.parse_topic_choice(content, topics)
        except (OSError, ValueError, KeyError, IndexError):
            topic_ids = None
    hits = study_ask.gather_candidates(index, [question], question, vector, SCRIPTURES_CONN, topic_ids)
    try:
        content = chat(chat_url, chat_model, study_ask.selection_messages([question], hits), 0.1)
        chosen = study_ask.parse_selection(content, len(hits))
    except (OSError, ValueError, KeyError, IndexError):
        chosen = None
    if not chosen:
        return study_ask.fallback_hits(hits), True
    return study_ask.by_tier(study_ask.with_minimums([hits[i] for i in chosen], hits, question)), False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("index_db")
    parser.add_argument("embeddings_url")
    parser.add_argument("model")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--select", nargs=2, metavar=("CHAT_URL", "CHAT_MODEL"))
    parser.add_argument(
        "--questions", default=str(QUESTIONS_PATH),
        help="question file (default: study_index_eval_questions.json; see also "
        "study_index_heldout_questions.json)",
    )
    parser.add_argument(
        "--scriptures-db", default=str(PROJECT_ROOT / "data" / "scriptures.db"),
        help="main database, for Topical Guide key passages (default: data/scriptures.db)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    global SCRIPTURES_CONN
    SCRIPTURES_CONN = sqlite3.connect(f"file:{args.scriptures_db}?mode=ro", uri=True)
    SCRIPTURES_CONN.row_factory = sqlite3.Row
    conn = sqlite3.connect(f"file:{args.index_db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    index = si.StudyIndex(conn)
    questions = json.loads(Path(args.questions).read_text(encoding="utf-8"))["questions"]

    mixed_ranks, scripture_ranks, selected_ranks, dupes, fallbacks = [], [], [], 0, 0
    for item in questions:
        vector = embed(args.embeddings_url, args.api_key, args.model, format_query(args.model, item["q"]))
        mixed = index.search(item["q"], vector, kind_limits=si_kind_limits(), limit=10)
        scripture = index.search(item["q"], vector, kinds={"scripture"}, limit=10)
        mixed_ranks.append([i for i, h in enumerate(mixed, 1) if is_relevant(h, item["refs"])])
        scripture_ranks.append([i for i, h in enumerate(scripture, 1) if is_relevant(h, item["refs"])])
        dupes += duplicate_slots(mixed)
        if args.select:
            chosen, fell_back = select(args.select[0], args.select[1], item["q"], vector, index)
            fallbacks += fell_back
            selected_ranks.append([i for i, h in enumerate(chosen, 1) if is_relevant(h, item["refs"])])
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
    if args.select:
        c5, c10, cmrr = score(selected_ranks)
        print(f"  selected:       hit@5 {c5:.0%}  hit@10 {c10:.0%}  MRR@10 {cmrr:.3f}"
              f"  ({fallbacks} fell back to index order)")
    print(f"  duplicate slots in mixed top 10: {dupes} of {10 * len(questions)}")


if __name__ == "__main__":
    main()
