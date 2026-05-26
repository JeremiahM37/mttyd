# mttyd

Make [ttyd](https://github.com/tsl0922/ttyd) usable on a phone.

A tiny HTTP server that wraps a ttyd-backed terminal in a mobile-friendly
page: legible font sizes, working touch scroll, a spellchecked command bar,
bash-history autocomplete, and tmux scrollback that survives browser
refreshes.

## Why

ttyd is great on desktops. On a phone it isn't:

| Problem | Why | mttyd's fix |
|---|---|---|
| Default font is unreadable on a 6" screen | ttyd's index page has no mobile viewport | Wrapper page sets `viewport`, scales xterm.js up |
| Touch scroll doesn't work | `.xterm-screen` swallows touch events before they reach the viewport | Custom `touchmove → term.scrollLines()` handler |
| Android autocorrect inserts duplicate words | Native `<datalist>` races Gboard's prediction strip | Replaced with a `<div>` dropdown that sets `input.value` directly |
| Reattaching to tmux shows empty scrollback | xterm.js's buffer starts empty per tab; tmux history isn't replayed | Wrapper script runs `tmux capture-pane -S -100000` before attach |
| Full-screen TUIs (claude, vim) hide history | tmux alternate-screen on | Recommended config disables it |

## Quick start

```bash
pip install mttyd

# in one shell, start ttyd attached to whatever you want exposed
ttyd -p 7681 -W tmux new-session -A -s main

# in another, point mttyd at that port
mttyd --config mttyd.yaml --port 8080
```

`mttyd.yaml`:
```yaml
ports:
  7681:
    history: { file: ~/.bash_history }
```

Open `http://your-server:8080/term/7681` on your phone.

The page is a single self-contained HTML document — xterm.js loads from a
CDN, the WebSocket connects directly to ttyd at `ws://host:7681/ws`, and
mttyd only ever serves the wrapper and the history endpoint.

## Configuration

Each port entry in `mttyd.yaml` declares one of:

- `history: { file: /path/to/.bash_history }` — read a local file
- `history: { ssh: user@host, path: ~/.bash_history }` — pull over SSH (uses your agent / keys)

Ports not in the config return 404 from `/term/{port}`. That's the access
control mechanism — keep the file tight.

Config-less mode (`mttyd` with no `--config`) skips the whitelist and
serves the wrapper for any port, with an empty history. Useful for one-off
LAN setups; **don't expose it to the internet that way.**

## Persistent sessions (the Claude+tmux mode)

The repo includes `tmux/pwa-claude-tmux`, a wrapper that:

- attaches to (or creates) a named tmux session
- dumps the existing scrollback before attaching so xterm.js sees history
- runs a long-running command inside, with auto-respawn

Default command is `claude --dangerously-skip-permissions`, but it's just an
env var:

```bash
cp tmux/pwa-claude-tmux ~/.local/bin/
chmod +x ~/.local/bin/pwa-claude-tmux

# Claude:
ttyd -p 7691 -W ~/.local/bin/pwa-claude-tmux

# Or anything else:
MTTYD_CMD="htop" MTTYD_SESSION="htop" ttyd -p 7692 -W ~/.local/bin/pwa-claude-tmux
```

Append `tmux/tmux.conf` to `~/.tmux.conf` for the matching tmux side
(mouse off, alt-screen disabled, big history-limit).

## Endpoints

| Method | Path | Returns |
|---|---|---|
| GET | `/term/{port}` | HTML wrapper page (404 if port not in config) |
| GET | `/api/term/history?port=N` | `{commands: [...], cached: bool}` |
| GET | `/healthz` | `{ok: true, ports: [...]}` |

## Tests

```bash
pip install -e '.[test]'
pytest
```

## License

[MIT](LICENSE)
