"""Sanity checks on the tmux wrapper script — the bits that have bitten us
before and would silently break the mobile experience if removed."""
from pathlib import Path

WRAPPER = Path(__file__).resolve().parent.parent / "tmux" / "pwa-claude-tmux"
TMUX_CONF = Path(__file__).resolve().parent.parent / "tmux" / "tmux.conf"


def test_wrapper_exists_and_is_executable():
    assert WRAPPER.is_file()
    import stat
    assert WRAPPER.stat().st_mode & stat.S_IXUSR


def test_wrapper_dumps_scrollback_on_attach():
    # Without `capture-pane`, the scrollback isnt replayed into xterm.js on
    # reattach and the user can only see the most-recent screen.
    assert "capture-pane" in WRAPPER.read_text()


def test_wrapper_starts_in_workdir_not_inherited_cwd():
    # Primary session lives in $HOME. Extra (user-spawned) sessions get
    # their own subdirectory under ~/.claude-sessions/$SESSION so Claude
    # treats each as an independent project. Either way, the wrapper must
    # cd somewhere deliberate before exec-ing tmux — not whatever inherited
    # CWD ttyd happened to have.
    body = WRAPPER.read_text()
    assert 'WORKDIR=' in body
    assert 'cd "$WORKDIR"' in body
    assert '-c "$WORKDIR"' in body
    assert '$HOME/.claude-sessions/' in body   # extra-session workdir scheme


def test_wrapper_unsets_claudecode_for_nested_session_bypass():
    # Claude Code refuses to launch with CLAUDECODE set in the env. The
    # wrapper unsets it so user-spawned tabs can actually open a new claude
    # alongside the one running in the parent tmux session.
    body = WRAPPER.read_text()
    assert "unset CLAUDECODE" in body


def test_tmux_conf_disables_alt_screen():
    # Alternate-screen-on means TUIs (claude, vim, less) draw to a screen
    # that doesnt land in xterm.js's scrollback. Must stay disabled.
    assert "smcup@:rmcup@" in TMUX_CONF.read_text()


def test_tmux_conf_disables_mouse():
    # Mouse off so touch/scroll passes through and the user isn't trapped
    # in copy-mode (which needs `q` to exit — hard on a phone keyboard).
    assert "set -g mouse off" in TMUX_CONF.read_text()
