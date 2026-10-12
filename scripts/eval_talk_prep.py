#!/usr/bin/env python3
"""Benchmark Talk Prep's scripture choices (src/scriptures/talk_prep.py)
against scripts/talk_prep_eval_topics.json - each topic run through the
same search the app uses (talk_prep.TalkPrepSearch), with the AI settings
stored in the database, or others given here to compare models.

    python3 scripts/eval_talk_prep.py DB [--chat-url URL] [--chat-model MODEL]
        [--api-key KEY] [--topic TEXT] [-v]

DB is a scriptures.db with its study_index.db beside it, built by the
embedding model its settings name - e.g. the snap's:

    python3 scripts/eval_talk_prep.py ~/snap/desktop-scriptures/common/scriptures.db

To compare another chat model on the same index (embeddings unchanged):

    python3 scripts/eval_talk_prep.py DB --chat-url https://api.anthropic.com \\
        --chat-model claude-opus-5-5 --api-key sk-ant-...

(Claude needs the `anthropic` package importable.)

For each topic, over the Standard Works passages returned:

- on-list: passages covering a verse listed in "expected";
- avoid: passages covering a verse listed in "avoid" (flagged off-topic);
- unlisted: the rest - not necessarily wrong, since the lists aren't
  exhaustive. -v prints them, to sort into "expected" or "avoid";
- coverage: the share of "expected" entries that appeared.

Precision (on-list / passages) is a floor, not the true figure, until the
unlisted passages have been sorted. Compare runs, not absolute numbers.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QTimer  # noqa: E402

from scriptures import study_index, talk_prep  # noqa: E402
from scriptures.ai_client import AiConfig, embeddings_config  # noqa: E402
from scriptures.data_access import get_setting  # noqa: E402
from scriptures.db import connect  # noqa: E402
from scriptures.study_ask import StudySearch  # noqa: E402

TOPICS_PATH = Path(__file__).resolve().parent / "talk_prep_eval_topics.json"
TIMEOUT_MS = 300_000
_REF_RE = re.compile(r"^(?:JST )?(?P<book>.+?) (?P<chapter>\d+)(?::(?P<start>\d+)(?:-(?P<end>\d+))?)?$")


def parse_ref(ref: str) -> tuple[str, int, int | None, int | None] | None:
    """("Alma", 34, 31, 34); a whole chapter has no verses."""
    match = _REF_RE.match(ref.strip())
    if not match:
        return None
    start = int(match["start"]) if match["start"] else None
    end = int(match["end"]) if match["end"] else start
    return match["book"], int(match["chapter"]), start, end


def covers(passage: tuple, listed: tuple) -> bool:
    """Whether a result passage and a listed reference share a verse."""
    if passage[:2] != listed[:2]:
        return False
    if passage[2] is None or listed[2] is None:  # a whole chapter covers all of it
        return True
    return passage[2] <= listed[3] and listed[2] <= passage[3]


def score(passages: list[str], expected: list[str], avoid: list[str]) -> dict:
    """Scores the Standard Works passage titles of one run."""
    parsed = [(title, parse_ref(title)) for title in passages]
    want = [(ref, parse_ref(ref)) for ref in expected]
    bad = [(ref, parse_ref(ref)) for ref in avoid]
    on_list, flagged, unlisted = [], [], []
    for title, passage in parsed:
        if passage is None:
            unlisted.append(title)
        elif any(covers(passage, ref) for _, ref in bad):
            flagged.append(title)
        elif any(covers(passage, ref) for _, ref in want):
            on_list.append(title)
        else:
            unlisted.append(title)
    found = [ref for ref, listed in want if any(p and covers(p, listed) for _, p in parsed)]
    return {"on_list": on_list, "avoid": flagged, "unlisted": unlisted, "found": found}


def study_search(conn: sqlite3.Connection, chat: AiConfig) -> StudySearch:
    model = get_setting(conn, "ai_embedding_model", "") or ""
    index_path = study_index.index_path_for(conn)
    if not model or not index_path.exists():
        sys.exit(f"No study index for this database (need an embedding model and {index_path}).")
    dimensions = get_setting(conn, "ai_embedding_dimensions", "") or ""
    stored_chat = AiConfig(
        get_setting(conn, "ai_api_base_url", "") or "", get_setting(conn, "ai_api_key", "") or "", ""
    )
    return StudySearch(
        index=study_index.StudyIndex(study_index.connect_index(index_path)),
        index_path=index_path,
        embedding_config=embeddings_config(
            stored_chat,
            get_setting(conn, "ai_embedding_base_url", "") or "",
            get_setting(conn, "ai_embedding_api_key", "") or "",
            model,
        ),
        embedding_dimensions=int(dimensions) if dimensions else None,
    )


def interview_for(case: dict) -> talk_prep.Interview:
    interview = talk_prep.Interview(topic=case["topic"], length=case.get("length", 10))
    interview.impressions = case.get("impressions", "")
    interview.directions = [case["direction"]] if case.get("direction") else []
    if case.get("reading"):
        interview.meeting = talk_prep.LESSON_MEETING
        interview.lesson_source = "block"
        interview.lesson_text = case["reading"]
    return interview


def run_case(app, conn, study, chat, case) -> tuple[list, str]:
    """(results, problem) - the app's own search for one topic."""
    outcome: list = []
    search = talk_prep.TalkPrepSearch(conn, study, chat, interview_for(case))
    search.succeeded.connect(lambda results, _note, _vector: (outcome.append((results, "")), app.quit()))
    search.failed.connect(lambda message, _key: (outcome.append(([], message)), app.quit()))
    QTimer.singleShot(TIMEOUT_MS, app.quit)
    app.exec()
    return outcome[0] if outcome else ([], "timed out")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("db", type=Path)
    parser.add_argument("--chat-url")
    parser.add_argument("--chat-model")
    parser.add_argument("--api-key")
    parser.add_argument("--topic", help="only topics containing this text")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    app = QCoreApplication.instance() or QCoreApplication([])
    conn = connect(args.db)
    chat = AiConfig(
        args.chat_url or get_setting(conn, "ai_api_base_url", "") or "",
        args.api_key if args.api_key is not None else get_setting(conn, "ai_api_key", "") or "",
        args.chat_model or get_setting(conn, "ai_model", "") or "",
    )
    study = study_search(conn, chat)
    study.index.adopt_arrays(study_index.StudyIndex.load_arrays(study.index_path))
    cases = json.loads(TOPICS_PATH.read_text(encoding="utf-8"))["topics"]
    if args.topic:
        cases = [c for c in cases if args.topic.lower() in c["topic"].lower()]
    print(f"Chat: {chat.model or '(default)'} at {chat.base_url}   Embeddings: {study.embedding_config.model}\n")

    totals = {"passages": 0, "on_list": 0, "avoid": 0, "expected": 0, "found": 0}
    for case in cases:
        label = case["topic"] + (f" ({case['reading']})" if case.get("reading") else "")
        started = time.time()
        results, problem = run_case(app, conn, study, chat, case)
        if problem:
            print(f"{label}: FAILED - {problem}")
            continue
        passages = [r.title for r in results if talk_prep.is_standard_works(conn, r)]
        s = score(passages, case["expected"], case.get("avoid", []))
        totals["passages"] += len(passages)
        totals["on_list"] += len(s["on_list"])
        totals["avoid"] += len(s["avoid"])
        totals["expected"] += len(case["expected"])
        totals["found"] += len(s["found"])
        print(
            f"{label}: {len(s['on_list'])}/{len(passages)} on-list, {len(s['avoid'])} avoid, "
            f"{len(s['unlisted'])} unlisted, coverage {len(s['found'])}/{len(case['expected'])} "
            f"({time.time() - started:.0f}s)"
        )
        if args.verbose:
            for title in s["avoid"]:
                print(f"    AVOID     {title}")
            for title in s["unlisted"]:
                print(f"    unlisted  {title}")

    if totals["passages"]:
        print(
            f"\nAll: {totals['on_list']}/{totals['passages']} on-list "
            f"({100 * totals['on_list'] / totals['passages']:.0f}% - a floor), "
            f"{totals['avoid']} avoid, coverage {totals['found']}/{totals['expected']} "
            f"({100 * totals['found'] / max(totals['expected'], 1):.0f}%)"
        )


if __name__ == "__main__":
    main()
