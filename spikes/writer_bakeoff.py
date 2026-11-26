"""Same lead story, same prompt, several Ollama Cloud models. Run on the Sprite from ~/station."""
import json
import sys
import time

from station.gateway import Gateway, GatewayError
from station.steps.rundown import Rundown
from station.steps.write import Chapter, messages_for, parse_story_reply, parse_turns, problems

MODELS = sys.argv[1].split(",")
run = "data/runs/test-friday"
rd = Rundown.from_dict(json.load(open(f"{run}/rundown.json")))
lead, secs = rd.stories[0], rd.seconds[rd.stories[0].post.id]
gw = Gateway()
for model in MODELS:
    t = time.time()
    try:
        r = gw.json("POST", "ollama", "/api/chat", {"model": model, "messages": messages_for("lead", lead, [lead.post], secs),
                                                    "stream": False, "think": False, "options": {"temperature": 0.4}}, timeout=180)
        h, s, script = parse_story_reply(r["message"]["content"])
        ch = Chapter(1, "lead", "Lead story", lead.post.id, parse_turns(script), h, s)
        words = sum(len(t.text.split()) for t in ch.turns)
        print(f"\n### {model}: {time.time()-t:.1f}s, {words} words (target {round(secs*2.8)}), "
              f"in/out tokens {r.get('prompt_eval_count')}/{r.get('eval_count')}, problems: {problems(ch, secs) or 'none'}")
        print("HEADLINE:", h)
        for turn in ch.turns:
            print(f"  {turn.speaker.upper()}: {turn.text}")
    except (GatewayError, ValueError, KeyError) as e:
        print(f"\n### {model}: FAILED after {time.time()-t:.1f}s: {str(e)[:200]}")
print("\nSOURCE POST:", json.dumps({k: lead.post.__dict__[k] for k in ("source", "title", "url", "text")})[:900])
