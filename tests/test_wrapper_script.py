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


def test_wrapper_starts_in_home_not_inherited_cwd():
    body = WRAPPER.read_text()
    assert 'cd "$HOME"' in body
    assert '-c "$HOME"' in body


def test_tmux_conf_disables_alt_screen():
    # Alternate-screen-on means TUIs (claude, vim, less) draw to a screen
    # that doesnt land in xterm.js's scrollback. Must stay disabled.
    assert "smcup@:rmcup@" in TMUX_CONF.read_text()


def test_tmux_conf_disables_mouse():
    # Mouse-on captures touch events for copy-mode, blocking the browser
    # viewport from scrolling on phones.
    assert "set -g mouse off" in TMUX_CONF.read_text()
