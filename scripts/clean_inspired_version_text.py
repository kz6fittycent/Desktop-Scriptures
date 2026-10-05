#!/usr/bin/env python3
"""Second-pass text cleanup for the already-imported Inspired Version
(Joseph Smith Translation) - the OCR artifacts import_inspired_version.py's
first pass left in about a third of its verses, found by checking every
word against the app's clean volumes rather than by eye. Operates in place
on data/scriptures.db; no need to re-download or re-parse the scan.

Usage:
    python3 scripts/clean_inspired_version_text.py [path-to-db] [--dry-run]

Every fix below is checked against two references the app already has,
so it repairs damage without guessing at wording:

- VOCABULARY: every word in the app's clean, typeset volumes (the KJV
  Bible, Book of Mormon, Doctrine and Covenants, Pearl of Great Price,
  Lectures on Faith, the Apocrypha). A JST word that's in it is left
  alone, however odd it looks next to the KJV - the Joseph Smith
  Translation changes wording on purpose.
- THE KJV PARALLEL: the KJV verse closest in wording, from the same book
  (the JST often numbers verses differently - its Genesis 22:4 is the
  KJV's 22:3 - so it's found by shared words, not by number, and used
  only if most of the wording matches). Most JST verses match it word for
  word, so where an OCR-damaged word sits opposite a KJV word it's a
  near-miss of, the KJV's spelling is the right one.

The fixes, in order:

1. Split words rejoined. The 1867 printing hyphenated words across line
   ends, and the OCR mostly lost the hyphen: "peo ple", "chil dren",
   "Be- cause". Two or three neighboring pieces are joined when the
   result is a real word and at least one piece isn't (or the hyphen was
   kept), or when the joined word is what the KJV parallel has and the
   split pair isn't ("for give" -> "forgive" only where the KJV says
   "forgive"), or when the pair never occurs as two words in the clean
   volumes but the joined word does, often ("Be hold" -> "Behold").
2. Stray symbols dropped: bullets, carets, pipes, backslashes, tildes,
   guillemets, pound signs, and angle brackets - none ever appear in this
   text - removed from inside a word when that leaves a real word
   ("w/ith" -> "with"), and dropped outright as tokens of their own.
   Leftover pieces of decorative drop caps ("J_", "JL", "XA.") go, and a
   "?" misread for "s" before punctuation is fixed ("clothe?," ->
   "clothes,"). Doubled commas and semicolons become single ones, and a ; : ? or !
   standing alone (the 1867 typesetting put a space before them) joins
   the word before it, as in the rest of the app's text.
3. Garbled words corrected from the KJV parallel: a word that isn't real
   and sits, in a word-by-word alignment, opposite a KJV word it closely
   resembles ("whi3h" opposite "which", "kilJed" opposite "killed")
   takes the KJV's spelling, keeping the JST's own capitalization and
   punctuation. A number is OCR damage too - the KJV and JST spell
   numbers out: "0" and "1" are "O" and "I", and any other number takes
   the short KJV word opposite it ("fed in 9 meadow" opposite "fed in a
   meadow").

   A word the 1867 printing simply spelled its own way is NOT a garbled
   word, and is kept: one in the system's English word list
   (/usr/share/dict/words, if present) at least five letters long
   ("sycamore", "Nathaniel"), or one that recurs in the JST three or
   more times and is either eight or more letters long ("showbread",
   "Nethinim" - the same long misreading three times over is unlikely) or
   six or more and not one OCR mix-up away from a common word
   ("ringstreaked" - but not "coineth", which is "cometh" misread).
4. Stray single letters - a lone "j" or "f" between words, from a speck
   or an ornament in the scan - are dropped where the KJV parallel has
   nothing there. ("a", "I" and "O" are real words and always kept.) A
   lone "j" is a misread semicolon, so it becomes one: "Nadab j Seled"
   -> "Nadab; Seled".
5. The OCR's usual letter mix-ups, where there's no KJV word to compare
   with (a passage only the JST has): "rn" or "in" read for "m", "ri"
   for "n", "tb" for "th", a stray "." or "," inside a word, and the like
   (OCR_CONFUSIONS). A word that isn't real becomes the real word one such
   swap away - "iny" -> "my", "arid" -> "and", "a.nd" -> "and" - only if
   that word is common in the clean volumes (at least COMMON times) and
   it's the only candidate, or by far the most common one.

CHAPTER SUMMARIES (chapters.title - each chapter's italic "argument"):
italic type read worse, with mix-ups of its own - "/i" or "Ji" or "fi"
for "h" ("T/ie", "S/iishak", "Tfie" -> "The", "Shishak") - and there's
no KJV parallel to compare with. They get fixes 1, 2 and 5, with
ITALIC_CONFUSIONS added to fix 5 and a lower bar for how common the
word must be (names like Athaliah are rarer than "and").

What's left after this - a word damaged in a passage the KJV doesn't
have, or damaged too badly to resemble anything - is reported, not
guessed at. Run with --dry-run to see the counts and a sample of changes
without writing.

Existing installs get the corrected text through db.sync_bundled_content,
which updates changed verse text and moves each highlight to stay on the
same words.
"""

from __future__ import annotations

import difflib
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "scriptures.db"
VOLUME_SLUG = "inspired-version"
CLEAN_VOLUMES = (
    "holy-bible", "book-of-mormon", "doctrine-and-covenants", "pearl-of-great-price",
    "lectures-on-faith", "apocrypha",
)

JUNK_CHARS = "•^|\\~«»£<>{}"
_WORD_RE = re.compile(r"[A-Za-z]+(?:'[a-z]+)?")
# Leading/trailing punctuation around a token's letters.
_SPLIT_RE = re.compile(r"^(\W*)(.*?)(\W*)$", re.S)
KEEP_SINGLE_LETTERS = {"a", "A", "I", "O"}
# What's left of a decorative drop cap the OCR split off ("J_", "JL", "XA.").
DROPCAP_SCRAP_RE = re.compile(r"J[L_]|_L|_|XA\.?|X\\_|J\\\.|JL\^I|J\^l|1_J|\\_J|XJL|jLJL|J_\.")
# (what the OCR read, what the page said) - for fix 5.
OCR_CONFUSIONS = (
    ("rn", "m"), ("in", "m"), ("ri", "n"), ("ii", "u"), ("li", "h"), ("cl", "d"), ("tb", "th"),
    ("b", "h"), ("c", "e"), ("e", "c"), ("1", "l"), ("l", "i"), ("i", "l"), ("J", "I"), ("f", "t"),
    ("t", "f"), ("o", "e"), ("u", "n"), ("n", "u"), ("y", "v"), (".", ""), (",", ""), ("'", ""),
)
COMMON = 20
ITALIC_CONFUSIONS = (("/i", "h"), ("Ji", "h"), ("fi", "h"), ("/t", "h"), ("/", ""), ("nf", "of"), ("J", "l"))
TITLE_COMMON = 3
DIGIT_LETTERS = {"0": "O", "1": "I"}
SYSTEM_WORDS = Path("/usr/share/dict/words")


class Vocabulary(set):
    """Every word in the clean volumes, plus how often each word and each
    neighboring pair of words occurs there - and the JST's own spellings
    that are kept as they are (see fix 3)."""

    def __init__(self, texts):
        super().__init__()
        self.words: Counter[str] = Counter()
        self.pairs: Counter[tuple[str, str]] = Counter()
        for text in texts:
            words = [w.lower() for w in _WORD_RE.findall(text)]
            self.words.update(words)
            self.pairs.update(zip(words, words[1:]))
        self.update(self.words)

    def add_own_spellings(self, jst_texts: list[str]) -> None:
        english = set()
        if SYSTEM_WORDS.exists():
            english = {w.strip().lower() for w in SYSTEM_WORDS.read_text(errors="ignore").split()}
        counts = Counter(w.lower() for text in jst_texts for w in re.findall(r"\b[A-Za-z]+\b", text))
        for word, count in counts.items():
            if word in self:
                continue
            if len(word) >= 5 and word in english:
                self.add(word)
            elif len(word) >= 8 and count >= 3 or len(word) >= 6 and count >= 3 and not _confusion_candidates(word, self):
                self.add(word)


def load_vocabulary(conn: sqlite3.Connection) -> Vocabulary:
    placeholders = ",".join("?" * len(CLEAN_VOLUMES))
    return Vocabulary(text for (text,) in conn.execute(
        "SELECT v.text FROM verses v JOIN chapters c ON c.id = v.chapter_id JOIN books b ON b.id = c.book_id "
        f"JOIN volumes vol ON vol.id = b.volume_id WHERE vol.slug IN ({placeholders})",
        CLEAN_VOLUMES,
    ))


class Parallels:
    """Finds a JST verse's closest KJV verse in the same book, by the
    words they share (rarer words counting for more)."""

    def __init__(self, conn: sqlite3.Connection):
        self.books: dict[str, list[str]] = {}
        self.index: dict[str, dict[str, set[int]]] = {}
        for book, text in conn.execute(
            "SELECT b.name, v.text FROM verses v JOIN chapters c ON c.id = v.chapter_id "
            "JOIN books b ON b.id = c.book_id JOIN volumes vol ON vol.id = b.volume_id "
            "WHERE vol.slug = 'holy-bible' ORDER BY c.chapter_number, v.verse_number"
        ):
            verses = self.books.setdefault(book, [])
            for word in set(w.lower() for w in _WORD_RE.findall(text)):
                self.index.setdefault(book, {}).setdefault(word, set()).add(len(verses))
            verses.append(text)

    def find(self, book: str, text: str) -> str:
        verses, index = self.books.get(book), self.index.get(book)
        if not verses:
            return ""
        scores: Counter[int] = Counter()
        for word in set(w.lower() for w in _WORD_RE.findall(text)):
            hits = index.get(word)
            if hits and len(hits) < len(verses) / 4:
                for i in hits:
                    scores[i] += 1 / len(hits)
        best, best_ratio = "", 0.0
        ours = [w.lower() for w in _WORD_RE.findall(text)]
        for i, _score in scores.most_common(5):
            theirs = [w.lower() for w in _WORD_RE.findall(verses[i])]
            ratio = difflib.SequenceMatcher(None, ours, theirs, autojunk=False).ratio()
            if ratio > best_ratio:
                best, best_ratio = verses[i], ratio
        return best if best_ratio >= 0.5 else ""


def _parts(token: str) -> tuple[str, str, str]:
    return _SPLIT_RE.match(token).groups()


def is_word(core: str, vocabulary: set[str]) -> bool:
    """A real word (or number, or hyphenated compound of real words)."""
    if not core:
        return False
    if core.isdigit():
        return True
    pieces = core.split("-")
    return all(p and _WORD_RE.fullmatch(p) and p.lower() in vocabulary for p in pieces)


def rejoin_split_words(tokens: list[str], vocabulary: set[str], parallel: str) -> list[str]:
    parallel_lower = f" {parallel.lower()} "
    out: list[str] = []
    i = 0
    while i < len(tokens):
        joined = None
        for size in (3, 2):
            group = tokens[i:i + size]
            if len(group) < size:
                continue
            leads = [_parts(t) for t in group]
            # Only the last piece may carry trailing punctuation (other than
            # a line-end hyphen), only the first leading punctuation.
            if any(trail.strip("-") for _l, _c, trail in leads[:-1]) or any(lead for lead, _c, _t in leads[1:]):
                continue
            cores = [core for _l, core, _t in leads]
            if not all(cores) or not all(c.replace("-", "").isalpha() for c in cores[:-1]):
                continue
            if not re.fullmatch(r"[A-Za-z]+(?:'[a-z]+)?", cores[-1]):
                continue
            word = "".join(c.rstrip("-") for c in cores)
            if not is_word(word, vocabulary):
                continue
            hyphenated = any(t.endswith("-") for _l, _c, t in leads[:-1]) or any(c.endswith("-") for c in cores[:-1])
            some_piece_unreal = not all(is_word(c.rstrip("-"), vocabulary) for c in cores)
            kjv_says_so = (
                f" {word.lower()}" in parallel_lower
                and " ".join(c.lower() for c in cores) not in parallel_lower
            )
            lowered = [c.rstrip("-").lower() for c in cores]
            never_apart = (
                size == 2
                and vocabulary.pairs[(lowered[0], lowered[1])] == 0
                and vocabulary.words[word.lower()] >= 20
            )
            if hyphenated or some_piece_unreal or kjv_says_so or never_apart:
                joined = leads[0][0] + word + leads[-1][2]
                i += size
                break
        if joined is None:
            out.append(tokens[i])
            i += 1
        else:
            out.append(joined)
    return out


def drop_junk(tokens: list[str], vocabulary: set[str]) -> list[str]:
    out = []
    for token in tokens:
        if out and re.fullmatch(r"[;:?!]+", token):
            out[-1] += token[0]  # "earth ;" -> "earth;"
            continue
        if not token.strip(JUNK_CHARS + ",.;:*'\"-"):
            if out and any(p in token for p in ",.;:") and not re.search(r"[,.;:]$", out[-1]):
                out[-1] += re.sub(r"[^,.;:]", "", token)[:1]  # keep its punctuation
            continue
        if any(ch in token for ch in JUNK_CHARS):
            lead, core, trail = _parts(token)
            stripped = core.translate({ord(ch): None for ch in JUNK_CHARS})
            trail = trail.translate({ord(ch): None for ch in JUNK_CHARS})
            lead = lead.translate({ord(ch): None for ch in JUNK_CHARS})
            if is_word(stripped, vocabulary) or not core:
                token = lead + stripped + trail
        if "/" in token:
            lead, core, trail = _parts(token)
            stripped = core.replace("/", "")
            if is_word(stripped, vocabulary):
                token = lead + stripped + trail
        token = re.sub(r"([,;])\1+", r"\1", token)
        # "?" misread for "s" before punctuation ("clothe?," -> "clothes,").
        q = re.fullmatch(r"([A-Za-z]+)\?([,;.:])", token)
        if q and is_word(q.group(1) + "s", vocabulary):
            token = q.group(1) + "s" + q.group(2)
        if DROPCAP_SCRAP_RE.fullmatch(token):
            continue
        if token:
            out.append(token)
    return out


def _similar(a: str, b: str) -> bool:
    a, b = a.lower(), b.lower()
    if abs(len(a) - len(b)) > 2:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.6


def _match_case(model: str, word: str) -> str:
    """The KJV's spelling in the JST word's case: all capitals ("AND"
    opening a chapter), or capitalized, or as the KJV has it."""
    if len(model) > 1 and model.isupper():
        return word.upper()
    if model[:1].isupper():
        return word[:1].upper() + word[1:]
    return word


def correct_from_parallel(tokens: list[str], vocabulary: set[str], parallel: str) -> list[str]:
    if not parallel:
        return tokens
    kjv = parallel.split()
    a = [re.sub(r"\W", "", t).lower() for t in tokens]
    b = [re.sub(r"\W", "", t).lower() for t in kjv]
    out = list(tokens)
    drop: set[int] = set()
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "replace" and i2 - i1 == j2 - j1:
            for i, j in zip(range(i1, i2), range(j1, j2)):
                lead, core, trail = _parts(tokens[i])
                _kl, kjv_core, _kt = _parts(kjv[j])
                if not kjv_core or not _WORD_RE.fullmatch(kjv_core):
                    continue
                if core in DIGIT_LETTERS:
                    out[i] = lead + DIGIT_LETTERS[core] + trail
                elif core.isdigit():
                    if len(kjv_core) <= 2:
                        out[i] = lead + kjv_core + trail
                elif not is_word(core, vocabulary) and _similar(core, kjv_core):
                    out[i] = lead + _match_case(core, kjv_core) + trail
        elif op == "delete":
            for i in range(i1, i2):
                lead, core, trail = _parts(tokens[i])
                if len(core) == 1 and core.isalpha() and core not in KEEP_SINGLE_LETTERS and not lead:
                    drop.add(i)
                    if core == "j" and i > 0 and not re.search(r"[,.;:!?]$", out[i - 1]):
                        out[i - 1] += ";"
    return [t for i, t in enumerate(out) if i not in drop]


def _confusion_candidates(
    core: str, vocabulary: Vocabulary, confusions=OCR_CONFUSIONS, common: int = COMMON
) -> Counter[str]:
    """Common real words one swap from `confusions` away from `core`."""
    candidates: Counter[str] = Counter()
    for seen, meant in confusions:
        start = core.find(seen)
        while start != -1:
            word = core[:start] + meant + core[start + len(seen):]
            count = vocabulary.words[word.lower()]
            if count >= common and _WORD_RE.fullmatch(word):
                candidates[word] = count
            start = core.find(seen, start + 1)
    return candidates


def fix_ocr_confusions(
    tokens: list[str], vocabulary: Vocabulary, confusions=OCR_CONFUSIONS, common: int = COMMON
) -> list[str]:
    out = []
    for token in tokens:
        lead, core, trail = _parts(token)
        if core and not is_word(core, vocabulary):
            ranked = _confusion_candidates(core, vocabulary, confusions, common).most_common(2)
            if ranked and (len(ranked) == 1 or ranked[0][1] >= 10 * ranked[1][1]):
                token = lead + _match_case(core, ranked[0][0]) + trail
        out.append(token)
    return out


def clean_verse(text: str, vocabulary: Vocabulary, parallel: str) -> str:
    tokens = text.split()
    tokens = drop_junk(tokens, vocabulary)
    tokens = rejoin_split_words(tokens, vocabulary, parallel)
    tokens = correct_from_parallel(tokens, vocabulary, parallel)
    tokens = fix_ocr_confusions(tokens, vocabulary)
    tokens = [
        lead + DIGIT_LETTERS[core] + trail if core in DIGIT_LETTERS else lead + core + trail
        for lead, core, trail in map(_parts, tokens)
    ]
    return " ".join(tokens)


def clean_title(title: str, vocabulary: Vocabulary) -> str:
    tokens = drop_junk(title.split(), vocabulary)
    tokens = rejoin_split_words(tokens, vocabulary, "")
    tokens = fix_ocr_confusions(tokens, vocabulary, OCR_CONFUSIONS + ITALIC_CONFUSIONS, TITLE_COMMON)
    return " ".join(
        lead + DIGIT_LETTERS.get(core, core) + trail for lead, core, trail in map(_parts, tokens)
    )


def unknown_words(text: str, vocabulary: set[str]) -> list[str]:
    return [core for _l, core, _t in map(_parts, text.split()) if core and not is_word(core, vocabulary)]


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry_run = "--dry-run" in sys.argv
    db_path = Path(args[0]) if args else DEFAULT_DB_PATH
    conn = sqlite3.connect(db_path)
    vocabulary = load_vocabulary(conn)
    parallels = Parallels(conn)
    rows = conn.execute(
        "SELECT v.id, b.name, c.chapter_number, v.verse_number, v.text, v.reference FROM verses v "
        "JOIN chapters c ON c.id = v.chapter_id JOIN books b ON b.id = c.book_id "
        "JOIN volumes vol ON vol.id = b.volume_id WHERE vol.slug = ? ORDER BY v.id",
        (VOLUME_SLUG,),
    ).fetchall()
    # The JST's own spellings are learned from text whose split words are
    # already rejoined - otherwise a frequent fragment ("gregation") would
    # pass for one.
    vocabulary.add_own_spellings([
        " ".join(rejoin_split_words(drop_junk(text.split(), vocabulary), vocabulary, parallels.find(book, text)))
        for _id, book, _c, _v, text, _r in rows
    ])
    before = after = changed = 0
    remaining: Counter[str] = Counter()
    samples = []
    for verse_id, book, chapter, verse, text, reference in rows:
        parallel = parallels.find(book, text)
        cleaned = clean_verse(text, vocabulary, parallel)
        before += len(unknown_words(text, vocabulary))
        left = unknown_words(cleaned, vocabulary)
        after += len(left)
        remaining.update(left)
        if cleaned != text:
            changed += 1
            if len(samples) < 40 and changed % 97 == 1:
                samples.append((reference, text, cleaned))
            if not dry_run:
                conn.execute("UPDATE verses SET text = ? WHERE id = ?", (cleaned, verse_id))
    titles = conn.execute(
        "SELECT c.id, c.title FROM chapters c JOIN books b ON b.id = c.book_id "
        "JOIN volumes vol ON vol.id = b.volume_id WHERE vol.slug = ? AND c.title IS NOT NULL",
        (VOLUME_SLUG,),
    ).fetchall()
    titles_changed = title_before = title_after = 0
    for chapter_id, title in titles:
        cleaned = clean_title(title, vocabulary)
        title_before += len(unknown_words(title, vocabulary))
        title_after += len(unknown_words(cleaned, vocabulary))
        if cleaned != title:
            titles_changed += 1
            if len(samples) < 60 and titles_changed % 40 == 1:
                samples.append((f"(summary, chapter id {chapter_id})", title, cleaned))
            if not dry_run:
                conn.execute("UPDATE chapters SET title = ? WHERE id = ?", (cleaned, chapter_id))
    if not dry_run:
        conn.commit()
        sys.path.insert(0, str(PROJECT_ROOT / "src"))
        from scriptures.db import compact

        compact(conn)
    print(f"{len(titles)} chapter summaries; {titles_changed} changed. Unrecognized words: {title_before} -> {title_after}.")
    print(f"{len(rows)} verses; {changed} changed. Unrecognized words: {before} -> {after}.")
    print("Most common left:", remaining.most_common(40))
    for reference, old, new in samples:
        print(f"\n{reference}\n  - {old}\n  + {new}")


if __name__ == "__main__":
    main()
