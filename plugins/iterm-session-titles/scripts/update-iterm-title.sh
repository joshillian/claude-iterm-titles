#!/bin/bash
# Updates iTerm2 tab title to match the Claude Code session name.
# Called by Stop and SessionStart hooks.

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')

if [ -z "$SESSION_ID" ]; then
  exit 0
fi

# Find the session file that matches this session ID
SESSION_NAME=""
for f in "$HOME/.claude/sessions"/*.json; do
  [ -f "$f" ] || continue
  fid=$(jq -r '.sessionId // empty' "$f" 2>/dev/null)
  if [ "$fid" = "$SESSION_ID" ]; then
    SESSION_NAME=$(jq -r '.name // empty' "$f" 2>/dev/null)
    # A "derived" name is Claude Code's own cwd-based placeholder (e.g. code-d5),
    # not something the user chose -- treat it as unnamed.
    NAME_SOURCE=$(jq -r '.nameSource // empty' "$f" 2>/dev/null)
    [ "$NAME_SOURCE" = "derived" ] && SESSION_NAME=""
    break
  fi
done

# No user-chosen name: snake_case the auto-generated title from the initial request
if [ -z "$SESSION_NAME" ]; then
  LOG=$(ls "$HOME/.claude/projects"/*/"$SESSION_ID.jsonl" 2>/dev/null | head -1)
  if [ -n "$LOG" ]; then
    AI_TITLE=$(grep -m1 '"type":"ai-title"' "$LOG" 2>/dev/null | jq -r '.aiTitle // empty')
    if [ -n "$AI_TITLE" ]; then
      SESSION_NAME=$(echo "$AI_TITLE" \
        | tr '[:upper:]' '[:lower:]' \
        | tr -cs 'a-z0-9' ' ' \
        | tr ' ' '\n' \
        | grep -vxE 'a|an|the|for|to|in|of|and|from|on|with|my|our|is|are|that|this' \
        | grep -vx '' \
        | head -4 \
        | paste -sd_ -)
    fi
  fi
fi

# Still nothing (title not written yet): fall back to dirname-timestamp from session start
if [ -z "$SESSION_NAME" ]; then
  DIR_NAME="${CWD##*/}"
  # Use the session file's startedAt to generate a stable timestamp
  if [ -n "$f" ] && [ -f "$f" ]; then
    STARTED_MS=$(jq -r '.startedAt // empty' "$f" 2>/dev/null)
    if [ -n "$STARTED_MS" ]; then
      STARTED_S=$((STARTED_MS / 1000))
      TIMESTAMP=$(date -r "$STARTED_S" '+%m%d%H%M' 2>/dev/null)
    fi
  fi
  TIMESTAMP="${TIMESTAMP:-$(date '+%m%d%H%M')}"
  SESSION_NAME="${DIR_NAME}-${TIMESTAMP}"
fi

# Hooks run without a controlling terminal, so /dev/tty fails. Walk up the
# process tree to find the claude process's tty and write there instead.
TTY_DEV=""
PID=$$
while [ -n "$PID" ] && [ "$PID" -gt 1 ]; do
  T=$(ps -o tty= -p "$PID" 2>/dev/null | tr -d ' ')
  if [ -n "$T" ] && [ "$T" != "??" ]; then
    TTY_DEV="/dev/$T"
    break
  fi
  PID=$(ps -o ppid= -p "$PID" 2>/dev/null | tr -d ' ')
done

[ -n "$TTY_DEV" ] || exit 0

# Set iTerm2 tab title via OSC escape sequence (write to tty, not stdout).
# iTerm treats this as a temporary override and drops it whenever the profile is
# re-applied (e.g. closing Settings), so it's only the fallback.
printf '\033]1;%s\007' "$SESSION_NAME" > "$TTY_DEV" 2>/dev/null

# Also set the iTerm session's own name (what "Edit Session" sets), which survives
# profile re-application. Matched by tty; values passed as argv, never interpolated.
# Opt out with CLAUDE_TITLE_ITERM_APPLESCRIPT=0.
if [ "${CLAUDE_TITLE_ITERM_APPLESCRIPT:-1}" != "0" ] && [ "$(uname)" = "Darwin" ] \
   && { [ "$TERM_PROGRAM" = "iTerm.app" ] || [ "$LC_TERMINAL" = "iTerm2" ]; }; then
  osascript - "$TTY_DEV" "$SESSION_NAME" >/dev/null 2>&1 <<'APPLESCRIPT'
on run argv
  set wantTty to item 1 of argv
  set newName to item 2 of argv
  tell application "iTerm2"
    repeat with w in windows
      repeat with tb in tabs of w
        repeat with s in sessions of tb
          if ((tty of s) as text) is wantTty then
            set name of s to newName
            return
          end if
        end repeat
      end repeat
    end repeat
  end tell
end run
APPLESCRIPT
fi

exit 0
