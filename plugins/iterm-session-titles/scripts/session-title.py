#!/usr/bin/env python3
"""UserPromptSubmit hook: set session title to "<gist>" or "<gist> [TICKET, ...]".

Ticket matching is opt-in: set CLAUDE_TITLE_TICKET_PROJECTS to a pipe-separated
list of project keys (e.g. "WEB|OPS") in your shell or settings.json "env".

Gist = Claude Code's own auto-generated ai-title from the transcript.
Tickets = JIRA keys mentioned in user prompts, or returned by a JIRA create
(Atlassian MCP createJiraIssue, or a Bash command that looks like a jira create).
Leaves user-chosen names (/rename) alone. Emits nothing when there's no change.
"""

import json
import os
import re
import sys
from pathlib import Path

PROJECTS = os.environ.get("CLAUDE_TITLE_TICKET_PROJECTS", "").strip()
KEY_RE = re.compile(rf"\b(?:{PROJECTS})-\d+\b") if re.fullmatch(r"[A-Z][A-Z0-9]*(\|[A-Z][A-Z0-9]*)*", PROJECTS) else None
MAX_KEYS = 3
OVERRIDABLE_SOURCES = {None, "", "derived", "auto", "hook"}


def name_source(session_id):
    for f in (Path.home() / ".claude" / "sessions").glob("*.json"):
        try:
            d = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if d.get("sessionId") == session_id:
            return d.get("nameSource")
    return None


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(text_of(c.get("text") or c.get("content")) for c in content if isinstance(c, dict))
    return ""


def is_jira_create(block):
    name = block.get("name", "")
    if "createJiraIssue" in name:
        return True
    cmd = (block.get("input") or {}).get("command", "")
    return name == "Bash" and re.search(r"jira\S*\s.*\bcreate\b", cmd) is not None


def scan(transcript, prompt):
    ai_title, keys, create_ids = None, [], set()

    def add(text):
        if KEY_RE is None:
            return
        for k in KEY_RE.findall(text or ""):
            if k not in keys:
                keys.append(k)

    try:
        lines = Path(transcript).open()
    except OSError:
        lines = []
    for line in lines:
        if '"ai-title"' not in line and '"tool_use"' not in line and '"user"' not in line:
            continue
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "ai-title":
            ai_title = e.get("aiTitle") or ai_title
            continue
        content = (e.get("message") or {}).get("content")
        if e.get("type") == "assistant" and isinstance(content, list):
            create_ids.update(b["id"] for b in content if b.get("type") == "tool_use" and is_jira_create(b))
        elif e.get("type") == "user":
            if isinstance(content, str):
                add(content)
            elif isinstance(content, list):
                for b in content:
                    if b.get("type") == "text":
                        add(b.get("text"))
                    elif b.get("type") == "tool_result" and b.get("tool_use_id") in create_ids:
                        add(text_of(b.get("content")))
    add(prompt)
    return ai_title, keys[:MAX_KEYS]


def main():
    data = json.load(sys.stdin)
    if name_source(data.get("session_id")) not in OVERRIDABLE_SOURCES:
        return
    ai_title, keys = scan(data.get("transcript_path", ""), data.get("prompt", ""))
    # Without a gist yet (first prompt), stay out of the way so Claude still generates one.
    if not ai_title:
        return
    title = f"{ai_title} [{', '.join(keys)}]" if keys else ai_title
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "sessionTitle": title}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
