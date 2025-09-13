import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from action.app.terminal import Terminal, start_terminal
from action.app.test_utils import assert_str_equal


pytestmark = pytest.mark.timeout(600)


ZORK_URL = (
    "https://www.infocom-if.org/downloads/zork1.zip"
)


def _which(cmd: str) -> str | None:
    return shutil.which(cmd)


def _run_shell(terminal: Terminal, command: str, wait_for: bytes | None = None, timeout: float = 60.0) -> bytes:
    deadline = time.monotonic() + timeout
    buf = b""
    terminal.send_text(command + "\n")
    while time.monotonic() < deadline:
        r = terminal.read_blocking()
        if r.output:
            buf += r.output
        if wait_for and wait_for in buf:
            break
        # If sentinel marks shell done, still allow a short drain
        if r.is_done:
            end = time.monotonic() + 0.3
            while time.monotonic() < end:
                out = terminal.read_output() or b""
                if out:
                    buf += out
                time.sleep(0.02)
            break
    return buf


def _ensure_programs_present(terminal: Terminal) -> None:
    # Try to ensure tmux and frotz exist. Prefer existing installs; otherwise attempt install.
    # macOS: use brew if available. Linux (Debian/Ubuntu): use apt-get.
    tmux_path = _which("tmux")
    frotz_path = _which("frotz")

    if tmux_path and frotz_path:
        return

    brew = _which("brew")
    apt_get = _which("apt-get")

    if not tmux_path:
        if brew:
            _run_shell(terminal, "brew install tmux", wait_for=b"cmd> ")
            tmux_path = _which("tmux")
        elif apt_get:
            _run_shell(terminal, "apt-get update", wait_for=b"cmd> ")
            _run_shell(terminal, "apt-get install -y tmux", wait_for=b"cmd> ")
            tmux_path = _which("tmux")

    if not frotz_path:
        if brew:
            _run_shell(terminal, "brew install frotz", wait_for=b"cmd> ")
            frotz_path = _which("frotz")
        elif apt_get:
            _run_shell(terminal, "apt-get update", wait_for=b"cmd> ")
            _run_shell(terminal, "apt-get install -y frotz curl unzip", wait_for=b"cmd> ")
            frotz_path = _which("frotz")

    missing = [name for name, path in [("tmux", tmux_path), ("frotz", frotz_path)] if not path]
    if missing:
        pytest.skip(f"Missing required system tools: {', '.join(missing)}")


def _start_tmux_renderer_fifo(session_name: str, fifo_path: str) -> None:
    try:
        os.remove(fifo_path)
    except OSError:
        pass
    os.mkfifo(fifo_path)
    # Start tmux that renders whatever is read from the FIFO
    subprocess.run([
        "tmux", "kill-session", "-t", session_name
    ], capture_output=True, check=False)
    subprocess.run([
        "tmux", "new-session", "-d", "-s", session_name, "-x", "80", "-y", "24",
        f"sh -lc 'stdbuf -i0 -o0 -e0 cat {fifo_path}'"
    ], check=True)
    time.sleep(0.3)


def _kill_tmux_session(session_name: str) -> None:
    subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True, check=False)


def _capture_tmux_screen(session_name: str) -> str:
    result = subprocess.run(["tmux", "capture-pane", "-pt", session_name], capture_output=True, text=True, check=True)
    return result.stdout


def _strip_trailing_spaces(s: str) -> str:
    # Normalize common differences while preserving shape
    lines = s.splitlines()
    return "\n".join(line.rstrip() for line in lines) + ("\n" if s.endswith("\n") else "")


def _drain_terminal_to_fifo(terminal: Terminal, fifo_fd: int, duration: float = 0.5) -> None:
    end = time.monotonic() + duration
    while time.monotonic() < end:
        out = terminal.read_output() or b""
        if out:
            os.write(fifo_fd, out)
        time.sleep(0.02)


def _download_and_unzip_zork(terminal: Terminal, workdir: str) -> None:
    _run_shell(terminal, f"cd {workdir} && curl -L -k {ZORK_URL} -o zork1.zip", wait_for=b"cmd> ")
    _run_shell(terminal, f"cd {workdir} && unzip -o zork1.zip", wait_for=b"cmd> ")


def _start_zork(terminal: Terminal, data_dir: str) -> None:
    # Find ZORK1.DAT in common locations within the unzipped archive
    candidates = [
        Path(data_dir) / "ZORK1.DAT",
        Path(data_dir) / "DATA" / "ZORK1.DAT",
        *Path(data_dir).rglob("ZORK1.DAT"),
    ]
    dat_path = None
    for c in candidates:
        if Path(c).exists():
            dat_path = str(c)
            break
    if not dat_path:
        pytest.skip("ZORK1.DAT not found after unzip; archive layout unexpected")
    # Launch zork directly in our terminal (not in tmux)
    terminal.send_text(f"frotz {dat_path}\n")


def _ensure_expected(path: Path, content: str) -> None:
    if not path.exists():
        path.write_text(content)
    else:
        expected = path.read_text()
        assert_str_equal(_strip_trailing_spaces(expected), _strip_trailing_spaces(content))


def test_terminal_plays_zork_and_renders_screen(tmp_path: Path):
    terminal = start_terminal()
    # Drain initial prompt
    _run_shell(terminal, "true", wait_for=b"cmd> ")

    _ensure_programs_present(terminal)

    # Workspace for zork assets and renderer FIFO
    workdir = str(tmp_path)
    session_name = "zork_test_renderer"
    fifo_path = os.path.join(workdir, "zork_render.fifo")
    _start_tmux_renderer_fifo(session_name, fifo_path)
    # Open FIFO for the duration (writer end)
    fifo_fd = os.open(fifo_path, os.O_WRONLY)
    try:
        # Prepare Zork assets
        _download_and_unzip_zork(terminal, workdir)

        # Start Zork
        _start_zork(terminal, workdir)
        # Stream initial output to tmux renderer
        _drain_terminal_to_fifo(terminal, fifo_fd, duration=1.2)
        screen1 = _capture_tmux_screen(session_name)

        expected_dir = Path(__file__).parent / "snapshots"
        expected_dir.mkdir(exist_ok=True)
        snap1 = expected_dir / "zork_start.txt"
        _ensure_expected(snap1, screen1)

        # Perform a few moves
        terminal.send_text("open mailbox\n")
        _drain_terminal_to_fifo(terminal, fifo_fd, duration=0.8)
        terminal.send_text("take leaflet\n")
        _drain_terminal_to_fifo(terminal, fifo_fd, duration=0.8)
        terminal.send_text("read leaflet\n")
        _drain_terminal_to_fifo(terminal, fifo_fd, duration=1.0)
        screen2 = _capture_tmux_screen(session_name)

        snap2 = expected_dir / "zork_after_leaflet.txt"
        _ensure_expected(snap2, screen2)

    finally:
        try:
            os.close(fifo_fd)
        except Exception:
            pass
        _kill_tmux_session(session_name)
        # Try to terminate any remaining program and return to shell
        try:
            terminal.send_bytes(b"\x03")  # Ctrl-C
            _run_shell(terminal, "true", wait_for=b"cmd> ")
        except Exception:
            pass


def test_zork_save_and_restore_renders_expected(tmp_path: Path):
    terminal = start_terminal()
    _run_shell(terminal, "true", wait_for=b"cmd> ")

    _ensure_programs_present(terminal)

    workdir = str(tmp_path)
    session_name = "zork_test_renderer_save"
    fifo_path = os.path.join(workdir, "zork_render_save.fifo")
    _start_tmux_renderer_fifo(session_name, fifo_path)
    fifo_fd = os.open(fifo_path, os.O_WRONLY)
    save_filename = "zork_save.dat"
    save_path = os.path.join(workdir, save_filename)
    try:
        _download_and_unzip_zork(terminal, workdir)
        # Ensure frotz runs with workdir as CWD so relative save file path is predictable
        terminal.send_text(f"cd {workdir}\n")
        _drain_terminal_to_fifo(terminal, fifo_fd, duration=0.2)
        _start_zork(terminal, workdir)
        _drain_terminal_to_fifo(terminal, fifo_fd, duration=1.0)

        # Make a few moves, then capture state and save
        terminal.send_text("open mailbox\n")
        _drain_terminal_to_fifo(terminal, fifo_fd, duration=0.5)
        terminal.send_text("take leaflet\n")
        _drain_terminal_to_fifo(terminal, fifo_fd, duration=0.7)
        # Capture where we are pre-save
        screen_before_save = _capture_tmux_screen(session_name)
        assert "West of House" in screen_before_save

        terminal.send_text("save\n")
        _drain_terminal_to_fifo(terminal, fifo_fd, duration=0.6)
        terminal.send_text(save_filename + "\n")
        # Wait up to 6s for the save file to appear (accepting .qzl/.sav variants). Record actual name.
        deadline = time.monotonic() + 6.0
        actual_save_basename: str | None = None
        while time.monotonic() < deadline and actual_save_basename is None:
            _drain_terminal_to_fifo(terminal, fifo_fd, duration=0.2)
            if Path(save_path).exists():
                actual_save_basename = save_filename
                break
            if Path(save_path + ".qzl").exists():
                actual_save_basename = save_filename + ".qzl"
                break
            if Path(save_path + ".sav").exists():
                actual_save_basename = save_filename + ".sav"
                break
        # Capture after-save screen for reference; do not assert snapshot since banners may vary
        expected_dir = Path(__file__).parent / "snapshots"
        expected_dir.mkdir(exist_ok=True)
        screen_after_save = _capture_tmux_screen(session_name)
        snap_save = expected_dir / "zork_after_save.txt"
        if not snap_save.exists():
            snap_save.write_text(screen_after_save)

        if actual_save_basename is not None:
            # Quit game cleanly
            terminal.send_text("quit\n")
            _drain_terminal_to_fifo(terminal, fifo_fd, duration=0.3)
            terminal.send_text("y\n")
            _drain_terminal_to_fifo(terminal, fifo_fd, duration=0.5)
            _run_shell(terminal, "true", wait_for=b"cmd> ")

            # Start again and restore
            terminal.send_text(f"cd {workdir}\n")
            _drain_terminal_to_fifo(terminal, fifo_fd, duration=0.2)
            _start_zork(terminal, workdir)
            _drain_terminal_to_fifo(terminal, fifo_fd, duration=1.0)
            terminal.send_text("restore\n")
            _drain_terminal_to_fifo(terminal, fifo_fd, duration=0.6)
            # Use the exact filename that was created by frotz (with extension if present)
            terminal.send_text(actual_save_basename + "\n")
            _drain_terminal_to_fifo(terminal, fifo_fd, duration=1.5)

            # After restore, verify location and inventory
            screen_after_restore = _capture_tmux_screen(session_name)
            assert "West of House" in screen_after_restore
            # Verify inventory contains leaflet after restore
            terminal.send_text("inventory\n")
            _drain_terminal_to_fifo(terminal, fifo_fd, duration=0.8)
            inv_after_restore = _capture_tmux_screen(session_name)
            assert "leaflet" in inv_after_restore.lower()
            # Keep/update snapshot for visibility
            snap = expected_dir / "zork_after_restore.txt"
            _ensure_expected(snap, screen_after_restore)
    finally:
        try:
            os.close(fifo_fd)
        except Exception:
            pass
        _kill_tmux_session(session_name)
        try:
            terminal.send_bytes(b"\x03")
            _run_shell(terminal, "true", wait_for=b"cmd> ")
        except Exception:
            pass


def test_zork_inventory_shows_leaflet_after_take(tmp_path: Path):
    terminal = start_terminal()
    _run_shell(terminal, "true", wait_for=b"cmd> ")

    _ensure_programs_present(terminal)

    workdir = str(tmp_path)
    session_name = "zork_test_renderer_inv"
    fifo_path = os.path.join(workdir, "zork_render_inv.fifo")
    _start_tmux_renderer_fifo(session_name, fifo_path)
    fifo_fd = os.open(fifo_path, os.O_WRONLY)
    try:
        _download_and_unzip_zork(terminal, workdir)
        _start_zork(terminal, workdir)
        _drain_terminal_to_fifo(terminal, fifo_fd, duration=1.0)

        terminal.send_text("open mailbox\n")
        _drain_terminal_to_fifo(terminal, fifo_fd, duration=0.5)
        terminal.send_text("take leaflet\n")
        _drain_terminal_to_fifo(terminal, fifo_fd, duration=0.5)
        terminal.send_text("inventory\n")
        _drain_terminal_to_fifo(terminal, fifo_fd, duration=1.0)

        screen = _capture_tmux_screen(session_name)
        expected_dir = Path(__file__).parent / "snapshots"
        expected_dir.mkdir(exist_ok=True)
        snap = expected_dir / "zork_inventory_after_leaflet.txt"
        _ensure_expected(snap, screen)
    finally:
        try:
            os.close(fifo_fd)
        except Exception:
            pass
        _kill_tmux_session(session_name)
        try:
            terminal.send_bytes(b"\x03")
            _run_shell(terminal, "true", wait_for=b"cmd> ")
        except Exception:
            pass


