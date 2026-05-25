"""Bash-history → ranked command suggestions for the command bar."""
from __future__ import annotations

import asyncio
import logging
from collections import Counter
from pathlib import Path

logger = logging.getLogger(__name__)


def rank_commands(history_text: str, limit: int = 200) -> list[str]:
    """Rank unique commands from raw bash_history text.

    Score = occurrences in the file + bonus for appearing in the last 30 lines.
    Lines that look like bash HISTTIMEFORMAT timestamps (`#1234567890`) and
    lines outside a sensible length range are dropped.
    """
    if not history_text:
        return []
    counts: Counter[str] = Counter()
    for line in history_text.splitlines():
        cmd = line.strip()
        if not cmd:
            continue
        if cmd.startswith("#") and cmd[1:].isdigit():
            continue
        if len(cmd) < 3 or len(cmd) > 250:
            continue
        counts[cmd] += 1
    recent_set = {ln.strip() for ln in history_text.splitlines()[-30:] if ln.strip()}

    def score(item):
        cmd, n = item
        bonus = 5 if cmd in recent_set else 0
        return -(n + bonus)

    return [c for c, _ in sorted(counts.items(), key=score)[:limit]]


async def read_history(source: dict) -> str:
    """Read bash_history for one port. Source is either:
        {"file": "/path/to/.bash_history"}
        {"ssh": "user@host", "path": "~/.bash_history"}
    """
    if "file" in source:
        path = Path(source["file"]).expanduser()
        if not path.is_file():
            return ""
        try:
            return path.read_text(errors="replace")
        except OSError as e:
            logger.warning("read history %s: %s", path, e)
            return ""
    if "ssh" in source:
        target = source["ssh"]
        remote_path = source.get("path", "~/.bash_history")
        cmd = [
            "ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=4", target, f"cat {remote_path}",
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=6)
            return out.decode("utf-8", errors="replace")
        except (asyncio.TimeoutError, OSError) as e:
            logger.warning("ssh history fetch %s: %s", target, e)
            return ""
    return ""
