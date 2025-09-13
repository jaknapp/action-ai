import select
import errno
import time
import os
import subprocess
from typing import List, Tuple
import pytest
from action.app.terminal import Terminal, get_fg_pgid, start_terminal

"""
REQUIREMENTS:

The terminal should be able to:
- Start up.
- Report is_done and the `cmd> ` prompt when it starts and finishes a command.
- Start up with an argv that allows us to always find it.
- Send text commands.
- Send text to a running command.
- Send signals.
- Send signals to a running command.
- Read binary data.
- Send binary data.
- Send binary data to a running command.
- Close itself on exit.
"""


pytestmark = pytest.mark.timeout(15)


def read_until_done_or_timeout(terminal: Terminal, timeout_s: float = 5.0, drain_after_s: float = 0.3) -> Tuple[bytes, List[str]]:
    """Read from PTY until the sentinel is received, or until timeout.

    Uses select with short slices to avoid indefinite blocking.
    """
    # Test-scoped timeout via pytest marker; rely on sentinel deterministically
    out_chunks: list[bytes] = []
    output_bytes = b""
    errors: list[str] = []
    is_done = False
    got_prompt = False
    while True:
        r, _, _ = select.select([terminal.sentinel_read_fd, terminal.master_fd], [], [], 0.1)
        if terminal.master_fd in r:
            chunk = terminal.read_output() or b""
            out_chunks.append(chunk)
            output_bytes += chunk
            if b"cmd> " in output_bytes:
                got_prompt = True
                break
        if terminal.sentinel_read_fd in r:
            # Drain the sentinel; one read is enough since we write small token
            try:
                _ = os.read(terminal.sentinel_read_fd, 16384)
            except OSError:
                pass
            is_done = True
            break
    # At this point we must have either seen the sentinel or the prompt

    # If we broke on prompt, output_bytes already contains it; otherwise join chunks
    if not output_bytes:
        output_bytes = b"".join(out_chunks)
    # After sentinel or prompt, drain pending output for a short window to capture prompt and trailing lines
    # Drain briefly to capture final prompt text
    cycles = int(drain_after_s / 0.05) if drain_after_s > 0 else 0
    for _ in range(cycles):
        r, _, _ = select.select([terminal.master_fd], [], [], 0.05)
        if terminal.master_fd in r:
            output_bytes += terminal.read_output() or b""
    # Best-effort: drain any pending sentinel tokens so subsequent calls start clean
    while True:
        r, _, _ = select.select([terminal.sentinel_read_fd], [], [], 0)
        if terminal.sentinel_read_fd not in r:
            break
        try:
            _ = os.read(terminal.sentinel_read_fd, 16384)
        except OSError as e:
            if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                break
            else:
                break
    return output_bytes, errors


def read_until_prompt(terminal: Terminal, timeout_s: float = 5.0) -> bytes:
    """Read only from master PTY until 'cmd> ' is observed or timeout."""
    deadline = time.monotonic() + timeout_s
    buf = b""
    nudged = False
    while time.monotonic() < deadline:
        r, _, _ = select.select([terminal.master_fd], [], [], 0.1)
        if terminal.master_fd in r:
            buf += terminal.read_output() or b""
            if b"cmd> " in buf:
                return buf
        # If no prompt yet after a short delay, send a newline to flush any partial line
        if not nudged and time.monotonic() > deadline - (timeout_s - 0.5):
            terminal.send_text("\n")
            nudged = True
    raise AssertionError("Timed out waiting for prompt on master_fd")


def read_until_contains(terminal: Terminal, needle: bytes, timeout_s: float = 5.0) -> bytes:
    """Read from master PTY until 'needle' is observed or timeout."""
    deadline = time.monotonic() + timeout_s
    buf = b""
    while time.monotonic() < deadline:
        r, _, _ = select.select([terminal.master_fd], [], [], 0.1)
        if terminal.master_fd in r:
            buf += terminal.read_output() or b""
            if needle in buf:
                return buf
    raise AssertionError(f"Timed out waiting for bytes: {needle!r}")


def read_until_any(terminal: Terminal, needles: list[bytes], timeout_s: float = 5.0) -> tuple[bytes, bytes]:
    """Read until any of the needles appears; returns (buffer, found_needle)."""
    deadline = time.monotonic() + timeout_s
    buf = b""
    while time.monotonic() < deadline:
        r, _, _ = select.select([terminal.master_fd], [], [], 0.1)
        if terminal.master_fd in r:
            buf += terminal.read_output() or b""
            for n in needles:
                if n in buf:
                    return buf, n
    raise AssertionError(f"Timed out waiting for any of: {[n for n in needles]!r}")

def test_terminal_start_up():
    terminal = start_terminal()

    output_bytes, error_list = read_until_done_or_timeout(terminal)

    assert error_list == []
    assert output_bytes.endswith(b'cmd> ')


def test_reports_done_and_prompt_after_command():
    terminal = start_terminal()
    # drain initial prompt
    _ = read_until_done_or_timeout(terminal)

    terminal.send_text('echo hi\n')
    output_bytes, error_list = read_until_done_or_timeout(terminal)

    assert error_list == []
    assert b'echo hi\r\nhi\r\n' in output_bytes
    assert output_bytes.endswith(b'cmd> ')


def test_startup_argv_identifiable():
    terminal = start_terminal()
    # allow process to initialize
    _ = read_until_done_or_timeout(terminal)

    ps_cmd = ['ps', '-o', 'command=', '-p', str(terminal.pid)]
    cmdline = subprocess.check_output(ps_cmd).decode('utf-8', errors='ignore')
    assert 'action-terminal' in cmdline


def test_send_text_commands():
    terminal = start_terminal()
    _ = read_until_done_or_timeout(terminal)

    terminal.send_text('echo hello\n')
    output_bytes, _ = read_until_done_or_timeout(terminal)
    assert b'echo hello\r\nhello\r\n' in output_bytes
    assert output_bytes.endswith(b'cmd> ')


def test_send_text_to_running_command():
    terminal = start_terminal()
    _ = read_until_done_or_timeout(terminal)

    terminal.send_text('cat\n')
    # Read the echo of the command (robust to sentinel events)
    _ = read_until_contains(terminal, b'cat\r\n')

    terminal.send_text('hello\n')
    # cat should echo back immediately
    _ = read_until_contains(terminal, b'hello\r\n')

    # end cat via EOF (Ctrl-D) and wait for prompt
    terminal.send_bytes(b"\x04")
    done_bytes, _ = read_until_done_or_timeout(terminal)
    assert b'cmd> ' in done_bytes


def test_send_signals_terminate_sleep():
    terminal = start_terminal()
    _ = read_until_done_or_timeout(terminal)

    terminal.send_text('sleep 60\n')
    # breakpoint()
    # Read echo
    read_output = terminal.read_blocking()
    # Wait for sleep command to start and get its own pgid
    start = time.monotonic()
    while True:
        pgid = get_fg_pgid(terminal.master_fd)
        if pgid != terminal.pid:
            break
        if time.monotonic() - start > 3.0:
            raise TimeoutError("Timed out waiting for sleep command to start")
        time.sleep(0.1)

    terminal.send_signal('SIGINT')
    out, _ = read_until_done_or_timeout(terminal)
    # shell prints prompt after interruption
    assert b'cmd> ' in out


def test_send_signal_to_running_program_handler():
    terminal = start_terminal()
    _ = read_until_done_or_timeout(terminal)

    python_cmd = (
        "python3 -c 'import signal,sys,time; "
        "signal.signal(2, lambda s,f: (sys.stdout.write(\"INT\\n\"), sys.stdout.flush())); "
        "print(\"RUN\"); sys.stdout.flush(); time.sleep(60) '\n"
    )
    terminal.send_text(python_cmd)
    # Read command echo and RUN line
    buf = b''
    while b'RUN\r\n' not in buf:
        chunk = terminal.read_blocking().output or b''
        buf += chunk

    terminal.send_signal('SIGINT')
    # Expect INT to be printed by handler
    buf += read_until_contains(terminal, b'INT\r\n', timeout_s=3.0)
    assert b'INT\r\n' in buf
    # Python handler keeps process alive; terminate it and then wait for prompt
    terminal.send_signal('SIGTERM')
    out2, _ = read_until_done_or_timeout(terminal)
    assert out2.endswith(b'cmd> ')


def test_read_binary_data():
    terminal = start_terminal()
    _ = read_until_done_or_timeout(terminal)

    terminal.send_text(
        "python3 -c 'import sys; sys.stdout.buffer.write(b" +
        '"\\x00\\x01\\xfe\\xffABC\\n"' +
        ")'\n"
    )
    # First ensure we actually see the binary payload (don't exit early on the prompt sentinel)
    seen = read_until_contains(terminal, b"\x00\x01\xfe\xffABC")
    assert b"\x00\x01\xfe\xffABC" in seen
    # Then allow the shell to complete and show the prompt
    out, _ = read_until_done_or_timeout(terminal)
    assert out.endswith(b'cmd> ')


def test_send_binary_data():
    terminal = start_terminal()
    _ = read_until_done_or_timeout(terminal)

    terminal.send_text(
        "python3 -c 'import sys; data=sys.stdin.buffer.read(4); sys.stdout.buffer.write(data)'\n"
    )
    # read echo of command
    _ = terminal.read_blocking()
    payload = b"\x00\xffA\n"
    expected_echo = payload.replace(b"\n", b"\r\n")
    terminal.send_bytes(payload)
    # Expect python to echo the payload back; wait until we see it
    echoed = read_until_contains(terminal, expected_echo)
    assert expected_echo in echoed
    # then finish and ensure prompt returns
    end, _ = read_until_done_or_timeout(terminal)
    assert end.endswith(b'cmd> ')


def test_send_binary_data_to_running_command():
    terminal = start_terminal()
    _ = read_until_done_or_timeout(terminal)

    terminal.send_text('cat\n')
    # ensure echo consumed
    _ = read_until_contains(terminal, b'cat\r\n')
    payload = b"\x00\xffA\n"
    terminal.send_bytes(payload)
    expected_echo = payload.replace(b"\n", b"\r\n")
    caret_echo = b"^@" + b"\xffA\r\n"
    echoed, found = read_until_any(terminal, [expected_echo, caret_echo])
    assert found in echoed
    # end cat with EOF and wait for prompt deterministically
    terminal.send_bytes(b"\x04")
    out, _ = read_until_done_or_timeout(terminal)
    assert b'cmd> ' in out


def test_close_itself_on_exit():
    terminal = start_terminal()
    _ = read_until_done_or_timeout(terminal)
    pid = terminal.pid

    terminal.close()

    # Deterministic: process group should not exist after close
    try:
        os.killpg(pid, 0)
        assert False, "Process group still exists after close()"
    except ProcessLookupError:
        pass
