# 003: GitHub Actions starts each hourly build from outside the Sprite

**Decision.** A scheduled GitHub Actions job runs at :48 each broadcast hour and tells the
Sprite to start a build, using a Sprites token stored as a GitHub secret. The Sprite sleeps
between builds.

**Why this came up.** A Sprite pauses about 30 seconds after it goes idle, and Fly's docs list
no way to wake one on a schedule. Thursday's check 5 found the opposite of what the docs
imply: a small loop left running inside the Sprite kept it awake for 14½ minutes and fired
every 30 seconds. So there were two workable designs, and getting it wrong means either missed
newscasts or a Sprite billing around the clock.

**Options.**
1. Outside cron (GitHub Actions) calls the Sprites exec API at :48. Cost: a token has to live in
   GitHub's secret store; GitHub warns scheduled runs can be delayed or dropped near the top of
   the hour.
2. A loop inside the Sprite waits until :48 and starts the build. Cost: the Sprite never sleeps,
   so it bills while awake all day; the cost was not measurable Thursday (the usage API showed
   zeros).
3. Both, with the inside loop as a backup. Cost: more moving parts to debug in a weekend.

**What we chose and why.** Option 1, Tarik's call (Claude recommended it). It keeps the
platform's "sleeps when idle" design that the entry is showing off, and the repo has to be on
GitHub anyway for the submission.

**What we gave up.** Exact timing: a delayed GitHub run means a late newscast. The demo hour is
triggered by hand regardless (PRD, "Real versus prepared").

**How we'll know if this was right.** Saturday's scheduled runs start by :52 and every
broadcast hour has a newscast. If runs arrive later, move the cron earlier or add option 3.

**What actually happened.**
