#!/usr/bin/env bash
# Check 5a: does a timer inside the Sprite keep firing after we disconnect and it goes idle?
# Starts a detached loop that appends a UTC timestamp every 30 s, then exits.
# Read the result later with:  sprite exec -s brave-indigo-lion -- cat ~/spikes/ticker.log
# Gaps much longer than 30 s mean the Sprite paused and the loop stopped running.
set -euo pipefail
mkdir -p ~/spikes
pkill -f 'spikes/ticker-loop' 2>/dev/null || true
cat > ~/spikes/ticker-loop.sh <<'LOOP'
#!/usr/bin/env bash
while true; do date -u +%H:%M:%S >> ~/spikes/ticker.log; sleep 30; done
LOOP
chmod +x ~/spikes/ticker-loop.sh
: > ~/spikes/ticker.log
nohup setsid ~/spikes/ticker-loop.sh > /dev/null 2>&1 < /dev/null &
sleep 1
echo "started at $(date -u +%H:%M:%S); log lines: $(wc -l < ~/spikes/ticker.log)"
