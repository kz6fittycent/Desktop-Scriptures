# CLAUDE.md - Desktop Scriptures

Working notes for AI-assisted sessions on this repo: how the owner wants
work done, where things stand, and what's next. Code-level detail lives in
module docstrings; this file points at them rather than repeating them.

## Where things stand

- **Released: 2.3.3** (2026-10-12, `d48a325`; snap on candidate, then
  promoted with `/promote <revision> stable done` on the call-for-testing
  issue). In it: Journal on the menu bar; Help → Report a Bug; Talk Prep;
  more AI providers (Claude, Gemini, OpenRouter, Groq, Mistral) with
  structured output; the Talk Prep benchmark.
- The user guide is the wiki: a separate repo,
  `git@github.com:kz6fittycent/Desktop-Scriptures.wiki.git`.
- Planned features: the README's **Roadmap** section.

## Next iteration

1. **"Update available" for the Windows/macOS builds** (they don't update
   themselves; users may not use Homebrew or Winget). Proposed, not yet
   agreed:
   - Frozen builds only (`paths.is_frozen()`).
   - Check GitHub's `/releases/latest` (it skips pre-releases) about once
     a day, under its own View toggle.
   - Show a menu-bar notice that opens one dialog with release notes and
     a download link.
   - No auto-install: the builds aren't code-signed. Sparkle/WinSparkle
     only once they are.
   - Open question: tell test-build users about newer test builds (a
     separate opt-in)?
2. **Then publish real Windows/macOS releases** from `v*` tags from then
   on (`.github/workflows/desktop-builds.yml` already builds one from a
   `v*` tag). Today only `test-v*` pre-releases exist, and old ones are
   deleted automatically. Move the README's Install section and roadmap
   item from "in testing" to released.
3. **Talk Prep quality:**
   - The user corrects the expected/avoid verses in
     `scripts/talk_prep_eval_topics.json`.
   - D&C 13:1 is a known stray (a talk on prayer with the direction
     "Priesthood and Personal Prayer"; "Strengthening families").
4. Older open items:
   - The JST is missing 2 John, 3 John, Jude, and Revelation (scan defect;
     see `scripts/import_inspired_version.py`).
   - v3.0 (geography, cited answers, content packs) and v4.0 (narration) on
     the Roadmap. A professional narrator has offered; recording everything
     (~130 h) vs a Piper voice fine-tuned on 1-3 h of samples is undecided,
     and needs his written consent first.

## How the owner wants work done

- **Versions** (`src/scriptures/__init__.py`):
  - Releases are x.y.z, and the patch wraps at .9 (2.0.9 → 2.1.0).
  - Unpushed work counts a fourth number (2.3.3.1, .2, ...), one per
    commit that changes the app.
  - The owner picks the release number; plain x.y.z is set just before the
    push.
- **Commit, don't push**, unless asked. A push to `main` builds the snap
  and publishes a candidate. Before pushing, `git fetch` and rebase: the
  scheduled citation refreshes merge their own PRs to `main`.
- **After every commit that changes app behavior, launch the app** for the
  owner to try. Skip this for docs/CI-only commits. Don't launch a second
  dev copy on top of a running one; the installed snap running alongside
  is fine:

  ```
  cd src/scriptures/ui && nohup python3 app.py /tmp/scriptures-live-test/scriptures.db > /tmp/scriptures-live-test/app.log 2>&1 &
  ```

  Stop it in a separate shell call: `pgrep -f`/`pkill -f` in the same
  command as the launch line matches the shell itself and kills it.
- **Release checklist:**
  1. The owner validates in the live app.
  2. README, the `snap/snapcraft.yaml` description (five sentences, under
     4,096 characters; fold new features in, no new paragraphs), and the
     wiki cover every change.
  3. Set the version and push.
- **The wiki is Claude's job**, after each feature. Walkthrough features
  get their own page and a sidebar entry; self-explanatory ones are folded
  into `Home.md`.
- **Don't commit `data/scriptures.db` drift** from local runs.
  `/tmp/scriptures-live-test/` holds the throwaway test copy.
- **No paid services.** The app is free, with zero budget for running it.
  The bug-report relay is on Cloudflare's free plan.
- Wording: say "not part of the Standard Works", never "not scripture".
  The user says Ensign and Liahona interchangeably.
- External links: one dialog with the link visible and clickable in it.
  `QDesktopServices.openUrl()` alone has failed silently before.
- Before building something custom, check briefly for an existing
  maintained solution.

## Design rules that matter

- **The AI never writes; it only chooses** from real candidates the app
  found. Every result is re-read from the app's own database. See the
  docstrings of `ask.py`, `study_ask.py`, and `talk_prep.py`.
- **Result order:** Standard Works, then General Conference talks, then
  Ensign/Liahona, then the rest.
- **Talk Prep's scripture** comes from what talks on the topic cite
  (TF-IDF-weighted citation consensus), not from the AI's judgment or raw
  embedding scores; both were measured and failed. Run
  `scripts/eval_talk_prep.py` before and after any change to it (baseline
  at 2.3.2.8: 79% on-list, 0 avoid).
- **AI requests all go through `ai_client.ChatRequest`.** OpenAI-compatible
  servers use Qt networking; Claude (base URL `api.anthropic.com`) uses
  the `anthropic` SDK (pinned 1.8.0) on a thread. Every request carries a
  JSON schema, with a fallback for servers that reject it.
- **Talk text is copyrighted.** The app stores only metadata (title,
  speaker, date, cited verses) and never fetches a talk's text.
- **Bug reports** go through the Cloudflare Worker in `relay/bug-report/`
  (live at `https://desktop-scriptures-bug-report.jimmy-tigert.workers.dev`).
  Its README covers setup and limits. The GitHub token behind it expires;
  until it's renewed (`npx wrangler@4 secret put GITHUB_TOKEN`), reports
  are saved and retried.

## Running things

- **Tests:** `for t in tests/test_*.py; do python3 $t; done` (no framework;
  each file runs on its own). `tests/test_ai_client.py` skips its Claude
  part unless the `anthropic` package can be imported.
- **Benchmarks:**
  - `scripts/eval_study_index.py`
  - `scripts/eval_talk_prep.py DB [-v] [--chat-url --chat-model --api-key]`

  Each needs a database and its own study index together, from the same
  install: a fresh bundled DB and an older install's index disagree on JST
  chapter ids.
- **The owner's AI setup:** gemma3-4b (inference snap, port 8328) for chat;
  embeddinggemma through Ollama for embeddings. The snap's data is in
  `~/snap/desktop-scriptures/common/`.
- **CI note:** GitHub's `ubuntu-latest` moves to Ubuntu 26 from 2026-10-19.
  Check that first if a build breaks after then.
