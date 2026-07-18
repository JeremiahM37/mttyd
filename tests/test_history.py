"""rank_commands — frequency × recency ordering; ssh command hardening."""
from mttyd.history import _ssh_cmd, rank_commands


def test_empty_input_returns_empty_list():
    assert rank_commands("") == []
    assert rank_commands("\n\n  \n") == []


def test_most_frequent_ranks_first():
    history = "\n".join(["git status"] * 5 + ["ls -la"] * 3 + ["pwd"] * 1)
    ranked = rank_commands(history)
    assert ranked[0] == "git status"
    assert ranked[1] == "ls -la"
    assert "pwd" in ranked


def test_recency_breaks_ties():
    # Both commands appear twice, but "recent one" is in the last 30 lines so
    # it gets a recency bonus.
    history_lines = ["old one", "old one"] + ["filler"] * 28 + ["recent one"] * 2
    ranked = rank_commands("\n".join(history_lines))
    assert ranked.index("recent one") < ranked.index("old one")


def test_drops_timestamps_and_short_lines():
    history = "\n".join([
        "#1700000000",      # HISTTIMEFORMAT timestamp
        "ls",               # too short (len < 3)
        "git status",
        "x" * 300,          # too long (len > 250)
        "git status",
    ])
    ranked = rank_commands(history)
    assert ranked == ["git status"]


def test_respects_limit():
    history = "\n".join(f"cmd-{i}" for i in range(500))
    assert len(rank_commands(history, limit=10)) == 10


def test_ssh_cmd_defaults_to_accept_new(monkeypatch):
    # `no` silently trusted changed host keys (MITM-friendly). Default is
    # accept-new: trust on first use, refuse a changed key.
    monkeypatch.delenv("MTTYD_SSH_STRICT_HOST_KEY_CHECKING", raising=False)
    cmd = _ssh_cmd("user@host", "~/.bash_history")
    assert "StrictHostKeyChecking=accept-new" in cmd
    assert "StrictHostKeyChecking=no" not in cmd
    assert cmd[-2:] == ["user@host", "cat ~/.bash_history"]


def test_ssh_cmd_host_key_policy_env_override(monkeypatch):
    monkeypatch.setenv("MTTYD_SSH_STRICT_HOST_KEY_CHECKING", "yes")
    assert "StrictHostKeyChecking=yes" in _ssh_cmd("u@h", "~/.bash_history")
