# CLAUDE.md - Desktop Scriptures

Working notes for AI-assisted sessions on this repo: how the owner wants
work done, where things stand, and what's next. Code-level detail lives in
module docstrings; this file points at them rather than repeating them.

## Where things stand

- **Released: 2.3.4** (2026-10-28; snap on candidate, then promoted with
  `/promote <revision> stable done` on the call-for-testing issue). In it:
  a verse can get just a tag (the entry no longer closes when moving from
  the note box to the tag box); OpenRouter for the study index (its
  embedding models are listed at `/embeddings/models`).
- 2.3.3 (2026-10-12): Journal on the menu bar; Help → Report a Bug; Talk
  Prep; more AI providers with structured output; the Talk Prep benchmark.
- Known flaky test: `tests/test_voices.py`'s corrupt-download case
  sometimes reports success (timing); fails roughly 1 run in 3.
- The user guide is the wiki: a separate repo,
  `git@github.com:kz6fittycent/Desktop-Scriptures.wiki.git`.
- Planned features: the README's **Roadmap** section.

## Next iteration

1. **"Update available" for the Windows/macOS builds: built 2026-10-28**
   (`app_updates.py`, `ui/app_update_dialog.py`; not released yet, no
   version bump by the owner's choice). Frozen builds only; daily check of
   `/releases/latest`; View → Check for App Updates; menu-bar button →
   dialog with the link.
   Desktop call-for-testing (test pre-releases, desktop-testing issues)
   dropped 2026-10-28 at the owner's request: pushes only build and
   smoke-test; /promote releases everything.
   **Package managers (set up 2026-10-28):**
   - Homebrew: tap `kz6fittycent/homebrew-tap` (~/git/homebrew-tap); its
     daily workflow writes `Casks/desktop-scriptures.rb` from the latest
     release. Empty until the first real release (2.3.4). Gatekeeper is
     left alone: the cask prints the Open Anyway steps.
   - Homebrew cask live at 2.3.4 (2026-10-28); README + wiki mention it.
   - Winget `kz6fittycent.DesktopScriptures`: first version submitted by
     hand as microsoft/winget-pkgs#464157 (hand-written 1.12.0 manifests,
     schema-validated; fork kz6fittycent/winget-pkgs). The owner must
     accept Microsoft's CLA on the PR. Once merged, add the Winget line
     to README/wiki; from then on desktop-builds.yml's `winget` job
     submits each release (WINGET_TOKEN: classic, public_repo, never
     expires). The 2.3.4 run's winget job failed only because the
     package didn't exist yet.
2. **Windows/macOS releases are automated (2026-10-28):** `/promote <rev>
   stable` (promote-to-stable.yml) also tags `v<version>` (version from the
   call-for-testing issue title; the newest `main` commit at that version)
   and starts `desktop-builds.yml` on the tag, which publishes the GitHub
   Release (marked latest). The first real one is whichever release is
   promoted next (2.3.4). README and wiki Installation now point at
   `releases/latest`.
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
  and publishes a candidate. (Not when a push only touches docs/CI files - the
  `paths-ignore` list in `snap-builds.yml`; anything else, like `src/` or
  `data/`, still builds.) Before pushing, `git fetch` and rebase: the
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
