# claude-iterm-titles

Claude Code plugin that:

- **Auto-titles sessions** from Claude Code's own generated title, optionally suffixed with ticket keys mentioned in your prompts (e.g. `fix login redirect [WEB-123]`). Names you set with `/rename` are left alone.
- **Mirrors the session title to the iTerm2 tab** on session start and after each turn.

## Install

```
/plugin marketplace add joshillian/claude-iterm-titles
/plugin install iterm-session-titles@joshillian-claude
```

Requires `jq` and `python3`. macOS + iTerm2 (the tab title uses OSC 1, so other terminals that honor it may work too).

## Ticket keys (optional)

Off by default. To enable, list your project keys in `~/.claude/settings.json`:

```json
{ "env": { "CLAUDE_TITLE_TICKET_PROJECTS": "WEB|OPS" } }
```

## Smart titles for generic sessions

Claude Code's title is generated from the first prompt only, so a session opened with a bare link ends up as "Slack thread" or "Code review request". When the title looks generic and `ANTHROPIC_API_KEY` is set, the hook asks Haiku for a better one from the first few prompts and Claude's replies. This happens at the 2nd and 6th prompt, and the result is cached per session.

- Off switch: `CLAUDE_TITLE_SMART=0`
- Model override: `CLAUDE_TITLE_MODEL` (default `claude-haiku-5-5`)
- Cost: about 1K input tokens, at most twice per generic session

## Caveat

Reads undocumented Claude Code internals (`~/.claude/sessions/*.json`, `ai-title` transcript entries). A Claude Code update may break it.
