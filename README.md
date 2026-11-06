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

## Caveat

Reads undocumented Claude Code internals (`~/.claude/sessions/*.json`, `ai-title` transcript entries). A Claude Code update may break it.
