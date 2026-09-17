#!/usr/bin/env python3
"""Second-pass text cleanup for already-imported Journal of Discourses
verses - catches OCR artifacts the import script's first pass didn't,
found by inspecting the imported text directly rather than the raw scans.
Operates in place on data/scriptures.db; no need to re-download or
re-parse the source djvu.xml files.

Usage:
    python3 scripts/clean_journal_of_discourses_text.py <path-to-db>

Four categories of artifact, all mechanical/high-confidence rather than
guesswork:

1. Embedded running-header/page-number fragments ("JOURNAL OF
   DISCOURSES. 161" mid-sentence). import_journal_of_discourses.py's
   RUNNING_HEADER_RE only drops a paragraph that is *entirely* that
   phrase - it misses the same fragment once OCR has already merged it
   into the middle of a real paragraph (a column-confusion artifact,
   same root cause as the paragraph-mid-sentence splits the import
   script's sentence-merge step handles). Matched case-SENSITIVE and
   only against the ALL-CAPS running-header form - "Journal of
   Discourses" or "journal of the events of their lives" appearing
   naturally in a sentence (real content, seen directly in this corpus)
   is left alone.

2. The SAME kind of running header, but showing the current discourse's
   own title instead of the book's ("PRIVILEGE OF THE SAINTS, ETC. 67"
   mid-sentence) - every discourse has a different one, so it can't be
   matched by fixed text the way "JOURNAL OF DISCOURSES" can. Matched
   generically instead: 2+ consecutive ALL-CAPS words directly followed
   by a 1-4 digit page number is a shape that essentially never occurs
   in this book's prose other than as this kind of header.

3. Long unreadable runs of "junk tokens" - stretches of many consecutive
   short (<=2-character) or digit-mixed-with-letter fragments from a
   badly corrupted scan region, with no discernible words (real example
   from this corpus: "t I d u le Ol Pp i i i . i - p tr 8a 3 In W in th
   W hu it sel S Pp ph Jes th mo wh Ch im"). A short word alone is
   completely normal English ("a", "to", "of", ...); a *run* of eight or
   more of them in a row, mostly not on a small whitelist of common
   short words, is not - real sentences don't do that. This can't
   recover what the run was supposed to say, so the run is dropped
   rather than left in as noise with negative reading value.

4. Stray symbol noise beyond what the import script already stripped
   (|^/): angle brackets, backslashes, tildes, and square brackets are
   never legitimate in this book's prose either. "?" is treated
   differently from the others - it's a real, common character in
   genuine sermon rhetorical questions (24,000+ occurrences in this
   corpus), so it's only removed when it's unambiguously OCR noise:
   sitting directly between two letters with no space (never how a real
   question mark appears). A noise character between two letters
   (mid-word) is deleted outright to rejoin the word; one that's already
   isolated becomes a space instead, so it still separates the words
   around it rather than fusing them together.

This does NOT attempt to fix word-level misspellings (e.g. OCR reading
"that" as "fat", "and" as "afd") - those are the OCR misreading one real
word as a different real word, not a stray symbol or unreadable-junk
span, so there's no nonsense token for the above to detect. A generic
dictionary spellchecker wouldn't flag them (they ARE real words) and
context-aware correction good enough to do this right (short of an LLM
rewriting the sermons - not attempted, since it risks silently changing
what a historical religious text actually says) is out of scope here.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures.db import connect  # noqa: E402

# Case-sensitive on purpose - see module docstring. "DISCOURS\w*" rather
# than a literal "DISCOURSES" so an OCR misread of that specific word
# (seen directly in this corpus: "DISCOURSKS") doesn't leave a stray
# half-stripped fragment behind - "discours-" as a stem is distinctive
# enough in English that this can't collide with a real different word.
EMBEDDED_RUNNING_HEADER_RE = re.compile(
    r"(?:\d{1,4}\s*)?JOURNAL OF(?:\s+DISCOURS\w*)?\.?,?(?:\s+VOL\.?\s*[IVXLCDM]+\.?)?"
)

# The per-discourse running header (its own title, not the book's) - see
# category 2 in the module docstring. 2+ consecutive ALL-CAPS words
# directly followed by a short number, a shape real prose in this book
# never otherwise takes.
RUNNING_HEADER_TITLE_RE = re.compile(
    r"\b(?:[A-Z]{2,}[,.'’]*\s+){1,7}[A-Z]{2,}[,.'’]*\s*\d{1,4}\b"
)

ALWAYS_NOISE_CHARS = set("|^/\\<>~[]")
CONTEXT_ONLY_NOISE_CHARS = set("?")

# See category 3 in the module docstring - short, common English words
# that are fine on their own and shouldn't count against a run just for
# being short.
SHORT_WORD_WHITELIST = {
    "i", "a", "to", "of", "in", "is", "it", "on", "he", "be", "we", "or",
    "as", "an", "by", "at", "if", "so", "no", "do", "my", "up", "us",
    "am", "go", "the", "and", "you", "thy", "thou", "me", "ye",
}
JUNK_RUN_MIN_LENGTH = 8
TOKEN_RE = re.compile(r"\S+|\s+")


def _is_junk_token(token: str) -> bool:
    core = re.sub(r"[^A-Za-z0-9]", "", token)
    if not core:
        return True
    if any(c.isdigit() for c in core) and any(c.isalpha() for c in core):
        return True
    return len(core) <= 2 and core.lower() not in SHORT_WORD_WHITELIST


def strip_junk_runs(text: str) -> str:
    """Drops any run of JUNK_RUN_MIN_LENGTH or more consecutive junk
    tokens (see category 3 in the module docstring) - preserves every
    other token and all original whitespace/newlines exactly."""
    tokens = TOKEN_RE.findall(text)
    word_positions = [i for i, t in enumerate(tokens) if not t.isspace()]
    if not word_positions:
        return text

    to_remove: set[int] = set()
    run_start = 0
    while run_start < len(word_positions):
        run_end = run_start
        while run_end < len(word_positions) and _is_junk_token(tokens[word_positions[run_end]]):
            run_end += 1
        if run_end - run_start >= JUNK_RUN_MIN_LENGTH:
            to_remove.update(word_positions[run_start:run_end])
        run_start = max(run_end, run_start + 1)

    if not to_remove:
        return text
    return "".join(tok for i, tok in enumerate(tokens) if i not in to_remove)


def clean_noise_chars(text: str) -> str:
    n = len(text)
    out = []
    for i, ch in enumerate(text):
        if ch not in ALWAYS_NOISE_CHARS and ch not in CONTEXT_ONLY_NOISE_CHARS:
            out.append(ch)
            continue
        before = text[i - 1] if i > 0 else ""
        after = text[i + 1] if i + 1 < n else ""
        mid_word = before.isalpha() and after.isalpha()
        if ch in CONTEXT_ONLY_NOISE_CHARS and not mid_word:
            out.append(ch)  # a real "?" - leave it alone
        else:
            out.append("" if mid_word else " ")
    return "".join(out)


def normalize_whitespace(text: str) -> str:
    """Collapses space/tab runs left by the removals above and drops any
    paragraph that turns out to have been pure noise, without disturbing
    the \\n\\n paragraph breaks between real paragraphs."""
    text = re.sub(r"[ \t]+", " ", text)
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    paragraphs = [p.strip() for p in text.split("\n\n")]
    paragraphs = [p for p in paragraphs if p]
    return "\n\n".join(paragraphs)


def clean_text(text: str) -> str:
    text = EMBEDDED_RUNNING_HEADER_RE.sub(" ", text)
    text = RUNNING_HEADER_TITLE_RE.sub(" ", text)
    text = strip_junk_runs(text)
    text = clean_noise_chars(text)
    return normalize_whitespace(text)


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    db_path = Path(sys.argv[1])
    conn = connect(db_path)

    rows = conn.execute(
        "SELECT v.id, v.text FROM verses v "
        "JOIN chapters c ON c.id = v.chapter_id "
        "JOIN books b ON b.id = c.book_id "
        "JOIN volumes vol ON vol.id = b.volume_id "
        "WHERE vol.slug = 'journal-of-discourses'"
    ).fetchall()

    changed = 0
    chars_removed = 0
    for row in rows:
        cleaned = clean_text(row["text"])
        if cleaned != row["text"]:
            chars_removed += len(row["text"]) - len(cleaned)
            conn.execute("UPDATE verses SET text = ? WHERE id = ?", (cleaned, row["id"]))
            changed += 1
    conn.commit()

    print(f"Verses inspected: {len(rows)}")
    print(f"Verses changed:   {changed}")
    print(f"Net characters removed: {chars_removed}")


if __name__ == "__main__":
    main()
