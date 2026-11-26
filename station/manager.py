"""Station manager: when a step fails, the headless Claude CLI picks one repair from a fixed menu.

The model only chooses an action and writes one sentence for the control room; code applies it.
Invocation proven in check 5: ANTHROPIC_BASE_URL = the Anthropic connector's gateway URL and a
placeholder token (the gateway attaches the real key). `--tools ""` (code.claude.com/docs/en/
cli-reference) gives the CLI no tools, so it can answer but never act.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from station.runlog import RunLog

MODEL = "claude-haiku-5-5"
TIMEOUT_S = 60
# What each step may do on failure. The first option is the default when the manager is unavailable.
FALLBACKS: dict[str, list[str]] = {
    "scrape": ["retry", "skip"], "dedupe": ["retry", "skip"], "judge": ["retry"], "rundown": ["retry"],
    "write": ["retry"], "voice": ["retry"], "assemble": ["retry"], "page": ["retry", "skip"],
    "publish": ["retry"], "archive": ["retry", "skip"], "finish": ["retry", "skip"], "video": ["retry", "skip"], "table": ["retry", "skip"],
}
SKIP_MEANS = {
    "scrape": "continue with no new posts; the rundown still considers recent unaired stories",
    "dedupe": "treat every post as its own story; Jev still judges each one",
    "page": "keep the previous pages online this hour",
    "archive": "skip the Box archive this hour; the files stay on the Sprite",
    "finish": "skip this hour's checkpoint and control-room refresh; the newscast is already public",
    "video": "skip today's video; the newscasts are unaffected",
    "table": "skip today's episode of The Table; the newscasts are unaffected",
}


@dataclass(frozen=True)
class ManagerDecision:
    action: str
    note: str


def commands() -> dict[str, Callable[[Path], None]]:
    from station.__main__ import COMMANDS

    return COMMANDS


def prompt(step: str, error: str, run: Path) -> str:
    options = [f'"retry": run the {step} step once more']
    if "skip" in FALLBACKS.get(step, []):
        options.append(f'"skip": {SKIP_MEANS[step]}')
    return (f"You are the station manager for an automated hourly radio newscast. The '{step}' step just failed "
            f"(run {run.name}) with this error:\n\n{error[-1500:]}\n\nChoose exactly one action:\n- "
            + "\n- ".join(options)
            + '\n\nReply with only a JSON object: {"action": "<action>", "note": "<one sentence for the public '
              'control room saying what failed and what you did>"}')


def claude_command(text: str) -> list[str]:
    return ["claude", "-p", text, "--model", MODEL, "--output-format", "json", "--tools", "", "--max-turns", "2"]


def ask_manager(step: str, text: str, runner=subprocess.run, base_url: str | None = None) -> ManagerDecision:
    default = FALLBACKS.get(step, ["retry"])[0]
    try:
        if base_url is None:
            from station.gateway import Gateway

            base_url = Gateway().base("anthropic")
        env = {**os.environ, "ANTHROPIC_BASE_URL": base_url, "ANTHROPIC_AUTH_TOKEN": "placeholder-gateway-attaches-real-key"}
        proc = runner(claude_command(text), capture_output=True, text=True, timeout=TIMEOUT_S, env=env)
        result = json.loads(proc.stdout)["result"]
        decision = json.loads(re.search(r"\{.*\}", result, re.S).group(0))
        action = decision.get("action")
        note = str(decision.get("note") or "").strip()[:300]
    except Exception as e:  # manager trouble must never block the build
        return ManagerDecision(default, f"Station manager unavailable ({type(e).__name__}); {default} applied.")
    if action not in FALLBACKS.get(step, ["retry"]):
        return ManagerDecision(default, f"{note} (manager chose an unknown action; {default} applied)".strip())
    return ManagerDecision(action, note or f"{step} failed; {action} applied.")


def _skip(step: str, run: Path) -> None:
    if step == "scrape":
        (run / "posts.json").write_text("[]")
    elif step == "dedupe":
        posts = json.loads((run / "posts.json").read_text())
        (run / "clusters.json").write_text(json.dumps(
            {"clusters": [{"primary_id": p["id"], "member_ids": [p["id"]]} for p in posts], "candidates": []}))


def _mark(run: Path, step: str, status: str, note: str) -> None:
    log = RunLog.open(run / "run_log.json", run_id=run.name)
    for s in reversed(log.steps):
        if s.name == step:
            s.status = status
            s.notes.append(note)
            break
    log.save()


def on_failure(step: str, exc: Exception, run: Path) -> bool:
    """Ask the manager, apply its choice, record the note. True means the build may continue."""
    decision = ask_manager(step, prompt(step, f"{type(exc).__name__}: {exc}", run))
    if decision.action == "skip":
        _skip(step, run)
        _mark(run, step, "repaired", decision.note)
        return True
    try:
        commands()[step](run)
    except Exception as again:
        _mark(run, step, "failed", f"{decision.note} Retry failed: {type(again).__name__}: {again}")
        return False
    _mark(run, step, "repaired", decision.note)
    return True
