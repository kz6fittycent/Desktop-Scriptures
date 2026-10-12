# Bug report relay

A Cloudflare Worker (free plan, no card) that turns the app's **Help → Report a Bug**
into a GitHub issue, so users don't need a GitHub account. How it keeps the tracker
clean (duplicate crashes become comments, rate limit, auto-close) is described at the
top of `worker.js`. Not part of the snap.

## One-time setup

1. **Cloudflare account:** sign up free at <https://dash.cloudflare.com/sign-up>, then open
   **Workers & Pages** once so the account gets its `<name>.workers.dev` subdomain.
2. **GitHub token:** <https://github.com/settings/personal-access-tokens/new>
   - Repository access: **Only select repositories** → `kz6fittycent/Desktop-Scriptures`
   - Permissions → Repository → **Issues: Read and write** (nothing else)
   - Expiration: the longest offered. When it expires, reports fail and the app saves
     them to a file instead; make a new token and repeat the `secret put` step.
     The argument is literally `GITHUB_TOKEN` (the name); paste the token only at the prompt.
3. **Label** the Worker files issues under:

   ```bash
   gh label create user-report --repo kz6fittycent/Desktop-Scriptures --color d93f0b --description "Filed from the app's Help → Report a Bug"
   ```

4. **Deploy** (the first `wrangler` run opens a browser to log in):

   ```bash
   cd relay/bug-report
   npx wrangler@4 login
   npx wrangler@4 deploy
   npx wrangler@4 secret put GITHUB_TOKEN
   ```

   `deploy` prints the address. **Live:** `https://desktop-scriptures-bug-report.jimmy-tigert.workers.dev`.
   The app posts to `<that address>/report`.

## Checking it

```bash
curl -s -X POST https://desktop-scriptures-bug-report.<name>.workers.dev/report \
  -H 'Content-Type: application/json' \
  -d '{"description":"Test report from setup - please close.","version":"test","platform":"curl"}'
```

That should answer with `{"issue":<number>,...}` and open a `user-report` issue. Logs:
`npx wrangler@4 tail`.
