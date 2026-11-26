#!/usr/bin/env bash
# Check 5b: can the preinstalled Claude CLI run headless with no key on the Sprite,
# by sending its API calls through the Anthropic connector?
# Per https://code.claude.com/docs/en/llm-gateway-connect (Context7 /websites/code_claude):
#   ANTHROPIC_BASE_URL = gateway base; a credential variable must be set, so we pass a
#   placeholder. The test passes only if the gateway replaces it with the stored key.
# Needs: an Anthropic connector granted to this Sprite. Cost: one tiny Claude request.
# Run:  sprite exec -s brave-indigo-lion --stdin -- bash -s < spikes/check5_station_manager.sh
set -uo pipefail
BASE=$(curl -s https://api.sprites.dev/v1/gateway/list | python3 -c '
import json,sys
d=json.load(sys.stdin)
c=[x for x in d.get("connections",[]) if x.get("provider")=="anthropic"]
print(c[0]["gateway_base_url"] if c else "")')
[ -n "$BASE" ] || { echo "No anthropic connection visible to this Sprite."; exit 1; }
echo "gateway base: $BASE"

echo "== raw Messages API call through the gateway (no auth header)"
curl -s -w '\nHTTP %{http_code}\n' "$BASE/v1/messages" \
  -H 'content-type: application/json' -H 'anthropic-version: 2023-06-01' \
  -d '{"model":"claude-haiku-5-5","max_tokens":20,"messages":[{"role":"user","content":"Reply with the word ok."}]}' | tail -c 600

echo "== claude -p headless through the gateway"
cd "$(mktemp -d)"
ANTHROPIC_BASE_URL="$BASE" ANTHROPIC_AUTH_TOKEN="placeholder-gateway-attaches-real-key" \
  timeout 120 claude -p "Reply with exactly: station manager online" \
  --model claude-haiku-5-5 --output-format json 2>&1 | tail -c 1500
echo "exit: $?"
