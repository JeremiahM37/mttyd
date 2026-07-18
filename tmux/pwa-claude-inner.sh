#!/bin/bash
# Inner respawn loop for pwa-claude-tmux. Kept in its OWN file (not inlined as a
# `bash -c '...'` string) on purpose: the old inline form was single-quoted, so a
# single apostrophe anywhere — even in a comment — silently broke the quoting and
# crash-looped the terminal. As a real file it's normal bash: apostrophes are
# fine, and `bash -n` can validate it independently.
#
# tmux launches this via `new-session -c "$WORKDIR"`, so our cwd is already the
# session's workdir; $HOME comes from the environment.

# Belt-and-suspenders: re-scrub the nesting guards in case the tmux server env
# snapshot still carried them into this child shell.
unset CLAUDECODE CLAUDE_CODE_SSE_PORT CLAUDE_CODE_ENTRYPOINT

# Leave Claude Code's mouse tracking ENABLED. Claude is a full-screen TUI that
# redraws in place, so its transcript never enters the xterm's (or tmux's) line
# scrollback — a local term.scrollLines() has nothing to move, which is why
# "scroll up" looked dead. With mouse tracking on, Claude scrolls its own
# transcript on wheel events, and the mttyd term.html forwards touch-drag as
# wheel events (only when the app has mouse tracking on), so finger-scroll now
# drives Claude's scrollback. We used to export CLAUDE_CODE_DISABLE_MOUSE=1 to
# work around the old client swallowing the gesture; the client now forwards it,
# so that workaround is gone. Unset here in case a stale value leaked in.
unset CLAUDE_CODE_DISABLE_MOUSE

# Claude encodes the cwd as a path with every non-alphanumeric char turned to
# "-". E.g. /home/admin/.claude-sessions/claude-2 becomes
# -home-admin--claude-sessions-claude-2.
PROJ_KEY=$(pwd | sed 's|[^a-zA-Z0-9-]|-|g')

# Respawn loop: if the inner command exits (WS drop, phone-screen-blank,
# crash), restart it.
#  - MTTYD_CMD, when set, replaces the default claude invocation entirely
#    (e.g. MTTYD_CMD="htop"). It's run through `bash -c` so a full command
#    line with arguments works.
#  - Otherwise, --continue auto-resumes the saved conversation for this
#    workdir, but only if one exists (a fresh workdir has no *.jsonl, and
#    --continue would error out and spin the loop), hence the compgen gate.
#  - --model opus pins every launch to the latest Opus so resumed threads don't
#    stay stuck on a stale generation.
while true; do
    if [ -n "$MTTYD_CMD" ]; then
        bash -c "$MTTYD_CMD"
    elif compgen -G "$HOME/.claude/projects/$PROJ_KEY/*.jsonl" >/dev/null 2>&1; then
        claude --continue --model opus --dangerously-skip-permissions
    else
        claude --model opus --dangerously-skip-permissions
    fi
    status=$?
    echo
    echo "[pwa-claude-tmux] inner command exited (status=$status). Press any key to restart, or Ctrl-C to drop to a shell."
    read -t 5 -n 1 && continue
    echo "auto-restarting in 1s..."
    sleep 1
done
