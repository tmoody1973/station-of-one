# 005 — The hourly trigger moves from GitHub Actions to a Cloudflare Worker

**Decision** — A Cloudflare Worker with a Cron Trigger starts each hourly build at :48; GitHub Actions keeps only a manual "Run workflow" button.

**Why this came up** — The station has no clock of its own: a Sprite sleeps when idle and has no scheduler, so something outside must wake it every hour. Decision 003 picked GitHub Actions' schedule as the least new setup. On Nov 26 the schedule was active but skipped both of its first slots (1:48 and 2:48 pm). GitHub documents that scheduled runs can be delayed or dropped at busy times, and the top of the hour is the busiest. If the trigger misses, a newscast simply doesn't happen — including, potentially, during the demo.

**Options**
1. **Cloudflare Worker Cron Trigger.** Fires on the minute; the Sprites token sits in Cloudflare's secret store. Cost: a Cloudflare account, one login, a 15-line Worker to maintain.
2. **cron-job.org.** No code, five minutes in a browser. Cost: a third party holds the Sprites token in plain job settings.
3. **Keep GitHub and hope.** Free and already built. Cost: proven unreliable on day one.

**What we chose and why** — Option 1. Tarik made the call; Claude recommended it. The Worker has no public web address, so it can only run on its schedule, and the token never enters the repo.

**What we gave up** — One more account and deploy step; Cloudflare's cron is UTC-only, so the schedule shifts an hour when daylight saving starts (the Sprite ignores out-of-hours runs, but the 7 am build would then come from the 6:48 UTC slot only after editing the cron).

**How we'll know if this was right** — Every :48 from 6:48 am to 6:48 pm Central produces a build line in `data/builds.log` and a success row in the Worker's Past Events, for a full day.

**What actually happened** —
