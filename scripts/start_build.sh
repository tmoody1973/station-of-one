#!/usr/bin/env bash
# Called by the hourly trigger (Cloudflare Worker cron -> Sprites exec API). Returns immediately;
# the build keeps the Sprite awake itself (Tasks API hold) and a lock prevents overlaps.
set -euo pipefail
cd "$HOME/station"
git pull -q --ff-only || echo "git pull failed; building with current code" >&2
mkdir -p data
# Hold the Sprite awake before answering the trigger. Without this it can fall asleep while uv starts
# (~30 s), freezing the build before Python takes its own hold (Nov 26-27: 7 pm-9 am builds frozen).
curl -s --max-time 10 --unix-socket /.sprite/api.sock -X PUT -H "Content-Type: application/json" \
  -d '{"expire": "10m"}' http://sprite/v1/tasks/build > /dev/null || echo "keep-awake hold failed" >&2
UV=/.sprite/bin/uv  # Sprite's uv (exec API shells may not have the login PATH)
[ -x "$UV" ] || UV=$(command -v uv)
nohup setsid "$UV" run python -m station build "$@" >> data/builds.log 2>&1 < /dev/null &
echo "build started (pid $!)"
