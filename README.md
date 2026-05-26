# mttyd

Make [ttyd](https://github.com/tsl0922/ttyd) usable on a phone.

A tiny HTTP server that wraps any ttyd-backed terminal in a mobile-friendly
page: proper viewport, smooth touch scroll with momentum, a key bar for
the arrows / Tab / Esc / Ctrl-C your phone keyboard hides, copy/paste,
search through scrollback, themes, and a settings drawer to toggle it all.

## Why

ttyd's own HTML works great on desktop. On a phone it falls apart:

| Problem | Why | mttyd's fix |
|---|---|---|
| Text looks weirdly small or huge | ttyd's index page has no mobile viewport, so phones render it at 980 px CSS and zoom out | Wrapper page sets `<meta name="viewport" content="width=device-width">` so font sizes mean what they say |
| Scroll doesn't work / pulls to refresh | xterm.js v5 doesn't translate touch into wheel events; the browser interprets a downward drag as pull-to-refresh and reloads the page | Pointer-event handler with `setPointerCapture`, anchored math, and friction-based momentum; `touch-action: none` on body kills pull-to-refresh |
| Android autocorrect inserts duplicate words | Gboard's predictive strip runs on xterm.js's hidden helper textarea | `inputmode="url"` + autocomplete/autocorrect/spellcheck off + a MutationObserver that re-applies the attrs if xterm.js ever resets them |
| Can't type arrows, Tab, Esc, Ctrl-C | Phone keyboards either lack these keys or hide them several taps deep | Bottom key bar with all of them; long-press for secondary keys (PgUp/PgDn/Home/End/Shift-Tab/Ctrl-D) |
| Reattaching to tmux shows empty scrollback | xterm.js's buffer starts empty per tab; tmux history isn't replayed | Optional wrapper script runs `tmux capture-pane -S -100000` before attach |
| Tmux alt-screen hides TUI history | Default tmux config | Recommended config disables it |

## Features

- **Smooth touch scroll** with momentum (Pointer Events + `setPointerCapture`, no event coalescing)
- **Key bar**: ↑ ↓ ← → Tab Esc ^C — long-press for PgUp/PgDn/Home/End/Shift-Tab/^D (haptic on long-press)
- **Top toolbar**: Find · Copy · Paste · ⚙
  - **Find** uses `@xterm/addon-search` for incremental search with highlights
  - **Copy** writes the current xterm.js selection to the system clipboard
  - **Paste** sends clipboard contents to the terminal as if typed
- **Settings drawer** (gear icon): font size, theme, per-feature toggles, snippet editor
- **5 themes**: Dark · Light · Solarized Dark · Dracula · Nord
- **Snippets bar**: optional horizontal row of one-tap commands (`label|command`, one per line)
- **Wake lock**: keeps the screen on while terminal is open; auto-releases when backgrounded
- **Auto-reconnect**: on WS close, retries 3× with exponential backoff (1s/2s/4s), then shows a manual reconnect button
- **Android Gboard fix**: hidden helper textarea attributes locked via MutationObserver

All settings persist to `localStorage` per-port and survive reload.

## Quick start

```bash
pip install mttyd

# in one shell: start ttyd on some port
ttyd -p 7681 -W tmux new-session -A -s main

# in another: point mttyd at it
mttyd --config mttyd.yaml --port 8080
```

`mttyd.yaml`:
```yaml
ports:
  7681:
    history: { file: ~/.bash_history }
```

Open `http://your-server:8080/term/7681` on your phone. (Or `--config`-less
for a single LAN box — see below.)

The page is a single self-contained HTML document. xterm.js + FitAddon +
SearchAddon load from a CDN, the WebSocket connects directly to ttyd at
`ws://host:7681/ws`, and mttyd only ever serves the wrapper page and the
optional bash-history endpoint.

## Configuration

Each port entry in `mttyd.yaml` declares one of:

- `history: { file: /path/to/.bash_history }` — read a local file
- `history: { ssh: user@host, path: ~/.bash_history }` — pull over SSH (uses your agent / keys)

Ports not listed return 404 from `/term/{port}`. That's the access-control
mechanism — keep the file tight.

Config-less mode (`mttyd` with no `--config`) skips the whitelist and serves
the wrapper for any port, with no history endpoint. Fine for one-off LAN
setups; **don't expose it to the public internet that way.**

## Persistent sessions (the Claude+tmux mode)

The repo includes `tmux/pwa-claude-tmux`, a wrapper script that:

- attaches to (or creates) a named tmux session
- dumps the existing scrollback into stdout before attaching, so xterm.js
  lands with the full conversation history
- runs a long-running command inside, with auto-respawn

Default command is `claude --dangerously-skip-permissions`, but it's just
two env vars:

```bash
cp tmux/pwa-claude-tmux ~/.local/bin/
chmod +x ~/.local/bin/pwa-claude-tmux

# Claude (default):
ttyd -p 7691 -W ~/.local/bin/pwa-claude-tmux

# Anything else:
MTTYD_CMD="htop" MTTYD_SESSION="htop" \
  ttyd -p 7692 -W ~/.local/bin/pwa-claude-tmux
```

Append `tmux/tmux.conf` to your `~/.tmux.conf` for the matching tmux side
(mouse off to avoid copy-mode trap on phone, alt-screen disabled, big
history-limit).

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

For end-to-end coverage there's a Playwright script that drives a headless
Chromium against a live mttyd, exercising every interactive feature; install
playwright and `playwright install chromium` to run it.

## License

[MIT](LICENSE)
