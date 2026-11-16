#!/usr/bin/env python3
"""UserPromptSubmit hook: set session title to "<gist>" or "<gist> [TICKET, ...]".

Ticket matching is opt-in: set CLAUDE_TITLE_TICKET_PROJECTS to a pipe-separated
list of project keys (e.g. "WEB|OPS") in your shell or settings.json "env".

Gist = Claude Code's own auto-generated ai-title from the transcript. That title is
derived from the first prompt only, so a session opened with a bare link gets a
generic name ("Slack thread", "Code review request") forever. When the gist looks
generic and ANTHROPIC_API_KEY is set, ask Haiku for a better one from the first few
prompts + Claude's replies, cached per session (regenerated at most at REGEN_AT turns).
Disable with CLAUDE_TITLE_SMART=0.

Tickets = JIRA keys mentioned in user prompts, or returned by a JIRA create
(Atlassian MCP createJiraIssue, or a Bash command that looks like a jira create).
Leaves user-chosen names (/rename) alone. Emits nothing when there's no change.
"""

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

PROJECTS = os.environ.get("CLAUDE_TITLE_TICKET_PROJECTS", "").strip()
KEY_RE = re.compile(rf"\b(?:{PROJECTS})-\d+\b") if re.fullmatch(r"[A-Z][A-Z0-9]*(\|[A-Z][A-Z0-9]*)*", PROJECTS) else None
MAX_KEYS = 3
OVERRIDABLE_SOURCES = {None, "", "derived", "auto", "hook"}

SMART = os.environ.get("CLAUDE_TITLE_SMART", "1") != "0"
MODEL = os.environ.get("CLAUDE_TITLE_MODEL", "claude-haiku-5-5")
REGEN_AT = (2, 6)  # user-turn counts at which to (re)generate a smart title
API_TIMEOUT = 6
MAX_WORDS = 8
GENERIC_RE = re.compile(
    r"\bslack\b|\bthread\b|\b[CDG][A-Z0-9]{8,}\b|\bp\d{10,}\b|\bpr \d+\b|"
    r"^(code review request|link review|url review|check (this )?link)$",
    re.I,
)
URL_RE = re.compile(r"https?://\S+")
CACHE_DIR = Path(
    os.environ.get("CLAUDE_PLUGIN_DATA")
    or Path.home() / ".claude" / "plugins" / "data" / "iterm-session-titles-joshillian-claude"
)


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


def is_real_prompt(text):
    t = (text or "").lstrip()
    return bool(t) and not t.startswith("<")  # skip command caveats, system reminders, etc.


def scan(transcript, prompt):
    ai_title, keys, create_ids = None, [], set()
    prompts, replies = [], []

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
        if '"ai-title"' not in line and '"assistant"' not in line and '"user"' not in line:
            continue
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "ai-title":
            ai_title = e.get("aiTitle") or ai_title
            continue
        if e.get("isSidechain") or e.get("isMeta"):
            continue
        content = (e.get("message") or {}).get("content")
        if e.get("type") == "assistant" and isinstance(content, list):
            create_ids.update(b["id"] for b in content if b.get("type") == "tool_use" and is_jira_create(b))
            for b in content:
                if b.get("type") == "text" and b.get("text", "").strip() and len(replies) < 4:
                    replies.append(b["text"].strip())
        elif e.get("type") == "user":
            if isinstance(content, str):
                add(content)
                if is_real_prompt(content):
                    prompts.append(content.strip())
            elif isinstance(content, list):
                for b in content:
                    if b.get("type") == "text":
                        add(b.get("text"))
                        if is_real_prompt(b.get("text")):
                            prompts.append(b["text"].strip())
                    elif b.get("type") == "tool_result" and b.get("tool_use_id") in create_ids:
                        add(text_of(b.get("content")))
    add(prompt)
    if is_real_prompt(prompt) and (not prompts or prompts[-1] != prompt.strip()):
        prompts.append(prompt.strip())
    return ai_title, keys[:MAX_KEYS], prompts, replies


def looks_generic(ai_title, prompts):
    if GENERIC_RE.search(ai_title):
        return True
    first = URL_RE.sub("", prompts[0]) if prompts else ""
    return bool(prompts) and URL_RE.search(prompts[0]) is not None and len(first.split()) < 4


def generate(prompts, replies):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    convo = "\n\n".join(
        [f"USER: {p[:600]}" for p in prompts[:4]] + [f"ASSISTANT: {r[:900]}" for r in replies[:3]]
    )
    body = {
        "model": MODEL,
        "max_tokens": 60,
        "thinking": {"type": "disabled"},
        "messages": [{
            "role": "user",
            "content": (
                "Write a 3-6 word title for this work session. Name the actual subject "
                "(system, dealer, error, feature, ticket topic). Never describe the medium: "
                "no 'Slack thread', 'link', 'URL', 'message', 'review request'. Sentence case, "
                "no quotes, no trailing punctuation. Output only the title.\n\n" + convo
            ),
        }],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=API_TIMEOUT) as r:
        out = json.load(r)
    text = "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text").strip()
    lines = text.splitlines()
    title = " ".join(lines[0].split()[:MAX_WORDS]).strip(" \"'`.*#:") if lines else ""
    return title[:80] or None


def smart_title(session_id, ai_title, prompts, replies):
    cache = CACHE_DIR / f"{session_id}.json"
    try:
        cached = json.loads(cache.read_text())
    except (OSError, ValueError):
        cached = {}
    turns = len(prompts)
    due = [t for t in REGEN_AT if turns >= t]
    if not due or not replies:
        return cached.get("title")
    if cached.get("title") and cached.get("at", 0) >= due[-1]:
        return cached["title"]
    try:
        title = generate(prompts, replies)
    except Exception:
        title = None
    if title:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"title": title, "at": due[-1], "ai_title": ai_title}))
        return title
    return cached.get("title")


def main():
    data = json.load(sys.stdin)
    session_id = data.get("session_id")
    if name_source(session_id) not in OVERRIDABLE_SOURCES:
        return
    ai_title, keys, prompts, replies = scan(data.get("transcript_path", ""), data.get("prompt", ""))
    # Without a gist yet (first prompt), stay out of the way so Claude still generates one.
    if not ai_title:
        return
    gist = ai_title
    if SMART and session_id and looks_generic(ai_title, prompts):
        gist = smart_title(session_id, ai_title, prompts, replies) or ai_title
    title = f"{gist} [{', '.join(keys)}]" if keys else gist
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "sessionTitle": title}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
