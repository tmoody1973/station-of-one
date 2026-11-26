#!/usr/bin/env bash
# Called by the hourly trigger (GitHub Actions -> Sprites exec API). Returns immediately;
# the build keeps the Sprite awake itself (Tasks API hold) and a lock prevents overlaps.
set -euo pipefail
cd "$HOME/station"
git pull -q --ff-only || echo "git pull failed; building with current code" >&2
mkdir -p data
UV=/.sprite/bin/uv  # Sprite's uv (exec API shells may not have the login PATH)
[ -x "$UV" ] || UV=$(command -v uv)
nohup setsid "$UV" run python -m station build "$@" >> data/builds.log 2>&1 < /dev/null &
echo "build started (pid $!)"
