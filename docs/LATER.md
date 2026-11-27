# After the hackathon

Work agreed to wait until everything in the current plans is built and tested. Not in scope before the
Nov 29 deadline (`docs/SPEC.md` fixes scope).

## Move the site to Next.js

Tarik, Nov 27: "let's do it after everything is built and tested."

- **Why:** a shared layout that stays mounted across page changes, so the player keeps playing natively
  (today `templates/shell.js` swaps `<main>` to do this, decision 010); React components; a familiar way
  to add interactive pages.
- **Why not now:** the listener sees no difference, the persistent player already works and is tested,
  and the rewrite (about 10 templates, a Node build step, every page and test re-verified) would cost
  1-1.5 days of the last 2. It also reopens the settled "static HTML, no web framework" architecture.
- **Start from:** the static export (pages stay files in the bucket, so they load while the Sprite sleeps)
  before considering server routes on Vercel. Keep the e2e tests in `tests/e2e/test_shell_nav.py` as the
  bar the new site must pass. Write it up as a decision-log entry when it starts.
