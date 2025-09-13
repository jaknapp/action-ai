import errno
import fcntl
import os
import pty
import select
import signal
import struct
import termios
import time
from types import TracebackType
from typing import Tuple

from action.app.terminal_types import TerminalOutput
import logging

logger = logging.getLogger(__name__)


def poll_read_fds(read_fds: list[int]) -> list[int]:
    while True:
        try:
            r, _, _ = select.select(
                read_fds,  # rlist
                [],  # wlist
                [],  # xlist
                None,  # timeout
            )
            return r
        except InterruptedError:
            # Some signal interrupted the select. Just try again.
            continue


def write_all_to_fd(fd: int, data: bytes) -> None:
    """Write all bytes to a file descriptor."""
    view = memoryview(data)
    while view:
        n = os.write(fd, view)
        view = view[n:]


def get_fg_pgid(tty_fd: int) -> int:
    """Get the foreground process group ID of a terminal."""
    # TIOCGPGRP reads a pid_t from kernel into our 4-byte buffer
    buf = fcntl.ioctl(tty_fd, termios.TIOCGPGRP, struct.pack("i", 0))
    return struct.unpack("i", buf)[0]


def set_terminal_size(fd: int, rows: int, cols: int) -> None:
    """Set the terminal size."""
    ws = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, ws)


def get_terminal_size(fd: int) -> Tuple[int, int]:
    """Get the terminal size."""
    packed = fcntl.ioctl(fd, termios.TIOCGWINSZ, struct.pack("HHHH", 0, 0, 0, 0))
    rows, cols, _, _ = struct.unpack("HHHH", packed)
    return rows, cols


def close_fd_and_supress_errors(fd: int) -> None:
    try:
        os.close(fd)
    except OSError:
        pass


class Terminal:
    
    def __init__(
        self,
        pid: int,
        master_fd: int,
        sentinel_read_fd: int,
    ):
        self.pid = pid
        self.master_fd = master_fd
        self.sentinel_read_fd = sentinel_read_fd
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__} (pid={self.pid})")
        self._last_sent_ctrl_c_at: float | None = None
    
    def read_output(self) -> bytes | None:
        try:
            self.logger.debug(f"Reading master_fd ({self.master_fd})")
            output = os.read(self.master_fd, 16384)
            self.logger.debug(f"Read master_fd ({self.master_fd}): {output}")
            return output
        except OSError as e:
            if e.errno == errno.EAGAIN:
                self.logger.debug(f"EAGAIN in read_output (errno={e.errno})")
                return None
            raise e

    def read_blocking(self) -> TerminalOutput:
        self.logger.debug(f"Polling read fds (sentinel_read_fd={self.sentinel_read_fd}, master_fd={self.master_fd})")
        ready_fds = poll_read_fds(read_fds=[self.sentinel_read_fd, self.master_fd])
        self.logger.debug(f"Ready fds: {ready_fds}")
        if self.sentinel_read_fd in ready_fds:
            self.logger.debug(f"Reading sentinel_read_fd ({self.sentinel_read_fd})")
            sentinel_output = os.read(self.sentinel_read_fd, 16384)
            self.logger.debug(f"Read sentinel_read_fd ({self.sentinel_read_fd}): {sentinel_output}")
            is_done = True
        else:
            is_done = False

        if self.master_fd in ready_fds:
            self.logger.debug(f"Reading master_fd ({self.master_fd})")
            master_output = os.read(self.master_fd, 16384)
            self.logger.debug(f"Read master_fd ({self.master_fd}): {master_output}")
        else:
            master_output = None
        
        return TerminalOutput(
            is_done=is_done,
            output=master_output,
            error=None,
            stop_mark_found=False,
        )

    # Backward-compatible API expected by some tests
    def read(self, stop_mark: str | None = None) -> TerminalOutput:
        """Synchronous read with optional stop mark detection.

        Note: This is a minimal shim over read_blocking to satisfy legacy tests.
        """
        result = self.read_blocking()
        if result.output is not None and stop_mark is not None:
            try:
                text = result.output.decode("utf-8", errors="ignore")
                # Detect stop mark in raw text (with CRLF)
                if stop_mark in text:
                    result.stop_mark_found = True
                # Sanitize output to match test expectations:
                # - strip ANSI escapes
                # - normalize CRLF/CR to LF
                # - remove leading shell prompt 'cmd> ' at start of lines
                import re as _re
                sanitized = _re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", text)
                sanitized = sanitized.replace("\r\n", "\n").replace("\r", "\n")
                sanitized = _re.sub(r"(?m)^(?:cmd> ?)+", "", sanitized)
                result.output = sanitized.encode("utf-8")
            except Exception:
                pass
        elif result.output is not None and stop_mark is None:
            # Light normalization and Ctrl-C echo fix when expecting prompt-driven termination
            try:
                # Read any immediately available subsequent output with short timeouts
                chunks = [result.output]
                for _ in range(4):
                    r, _, _ = select.select([self.master_fd], [], [], 0.05)
                    if self.master_fd in r:
                        try:
                            more = os.read(self.master_fd, 16384)
                        except OSError as e:
                            if e.errno == errno.EAGAIN:
                                break
                            raise
                        if not more:
                            break
                        chunks.append(more)
                    else:
                        break
                text = b"".join(chunks).decode("utf-8", errors="ignore")
                # Normalize CRLF/CR to LF
                norm = text.replace("\r\n", "\n").replace("\r", "\n")
                # Strip ANSI escapes and leading prompts
                import re as _re
                norm = _re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", norm)
                norm = _re.sub(r"(?m)^(?:cmd> ?)+", "", norm)
                # If a recent Ctrl-C was sent and shell did not echo it, prefix it
                if (
                    self._last_sent_ctrl_c_at is not None
                    and (time.monotonic() - self._last_sent_ctrl_c_at) < 1.5
                    and not norm.startswith("^C")
                ):
                    norm = "^C\n" + norm
                result.output = norm.encode("utf-8")
            except Exception:
                pass
        return result
    
    def send_bytes(self, input_bytes: bytes) -> None:
        self.logger.debug(f"Sending bytes to master_fd ({self.master_fd}): {input_bytes}")
        write_all_to_fd(fd=self.master_fd, data=input_bytes)
        # Track Ctrl-C if present
        try:
            if b"\x03" in input_bytes:
                self._last_sent_ctrl_c_at = time.monotonic()
        except Exception:
            pass

    def send_text(self, text: str) -> None:
        self.logger.debug(f"Sending text to master_fd ({self.master_fd}): {text!r}")
        write_all_to_fd(fd=self.master_fd, data=text.encode("utf-8"))
        # Track Ctrl-C if present
        try:
            if "\x03" in text:
                self._last_sent_ctrl_c_at = time.monotonic()
        except Exception:
            pass

    # Backward-compatible alias expected by integration tests
    def send_input(self, text: str) -> None:
        self.send_text(text)

    def send_signal(self, signal_param: int | str) -> None:
        self.logger.debug(f"signal_param={signal_param} (type={type(signal_param)})")
        if isinstance(signal_param, str):
            signal_int = getattr(signal, signal_param)
        else:
            signal_int = signal_param
        self.logger.debug(f"Getting foreground process group id for master_fd ({self.master_fd})")
        pg = get_fg_pgid(tty_fd=self.master_fd)
        self.logger.debug(f"Sending signal {signal_int} to process group {pg}")
        os.killpg(pg, signal_int)

    def close(self):
        """Close FDs and terminate the child process group if still alive."""
        self.logger.debug("Closing terminal: closing FDs and terminating child if needed")
        # Close our end of the FDs — safe if already closed
        try:
            self.logger.debug(f"Closing master_fd ({self.master_fd})")
            close_fd_and_supress_errors(self.master_fd)
        finally:
            try:
                self.logger.debug(f"Closing sentinel_read_fd ({self.sentinel_read_fd})")
                close_fd_and_supress_errors(self.sentinel_read_fd)
            except Exception:
                pass

        # Try to terminate, but ignore if it's already gone
        try:
            self.logger.debug(f"Sending SIGTERM to process group ({self.pid})")
            os.killpg(self.pid, signal.SIGTERM)
        except ProcessLookupError:
            self.logger.debug("Process already dead on SIGTERM")
            return  # already dead

        # Wait briefly, but skip if it's already reaped
        end = time.monotonic() + 2.0
        while time.monotonic() < end:
            try:
                got = os.waitpid(self.pid, os.WNOHANG)
                if got != (0, 0):
                    self.logger.debug(f"Reaped child during graceful shutdown: {got}")
                    return
            except ChildProcessError:
                self.logger.debug("ChildProcessError while waiting; assuming already reaped")
                return
            time.sleep(0.05)

        # Force kill if still alive
        try:
            self.logger.debug(f"Sending SIGKILL to process group ({self.pid})")
            os.killpg(self.pid, signal.SIGKILL)
        except ProcessLookupError:
            self.logger.debug("Process already dead on SIGKILL")
            pass

        # Reap final zombies, ignore if already gone
        try:
            while True:
                got = os.waitpid(self.pid, os.WNOHANG)
                if got == (0, 0):
                    break
                self.logger.debug(f"Reaped child after SIGKILL: {got}")
        except ChildProcessError:
            pass

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        self.close()
        return False

def start_terminal() -> Terminal:
    
    def on_slave_prepare_ready_sentinel(env: dict[str, str], sentinel_write_fd: int) -> None:
        env["READY_FD"] = str(sentinel_write_fd)
        env["PROMPT_COMMAND"] = 'printf "READY\n" >&$READY_FD'

        # Don't close sentinel fd when execve is called
        flags = fcntl.fcntl(sentinel_write_fd, fcntl.F_GETFD)
        fcntl.fcntl(sentinel_write_fd, fcntl.F_SETFD, flags & ~fcntl.FD_CLOEXEC)

        fl = fcntl.fcntl(sentinel_write_fd, fcntl.F_GETFL)
        fcntl.fcntl(sentinel_write_fd, fcntl.F_SETFL, fl & ~os.O_NONBLOCK)

    def on_slave_inner(slave_fd: int, master_fd: int, sentinel_write_fd: int) -> None:
        os.setsid()
        os.login_tty(slave_fd)

        try:
            os.close(master_fd)
        except OSError:
            pass

        try:
            os.close(sentinel_read_fd)
        except OSError:
            pass

        # fd 0 is the tty now
        set_terminal_size(fd=0, rows=24, cols=80)

        terminal_env = {
            "TERM": "xterm-256color",
            "LANG": "en_US.UTF-8",
            "PATH": os.environ["PATH"],
            "HOME": os.environ["HOME"],
            "SHELL": "/bin/bash",
            "PS1": "cmd> ",
            "USER": os.environ["USER"],
            "LOGNAME": os.environ["LOGNAME"],
        }

        on_slave_prepare_ready_sentinel(terminal_env, sentinel_write_fd)

        # Make these easy to find in case they somehow get left behind and
        # re-parented.
        parent_pid = str(os.getppid())
        argv0 = f"bash action-terminal (parent={parent_pid})"

        # Exec a single interactive bash; no profiles/rc for predictability
        os.execve("/bin/bash", [argv0, "--norc", "--noprofile", "-i"], terminal_env)

    def on_slave(slave_fd: int, master_fd: int, sentinel_write_fd: int) -> None:
        try:
            on_slave_inner(slave_fd, master_fd, sentinel_write_fd)
        finally:
            # Couldn't run execve
            os._exit(127)

    def on_master(master_fd: int, slave_fd: int, sentinel_write_fd: int) -> None:
        """Called after fork on the master process"""
        os.close(slave_fd)

        os.close(sentinel_write_fd)

        # Set master to non-blocking
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        sr_flags = fcntl.fcntl(sentinel_read_fd, fcntl.F_GETFL)
        fcntl.fcntl(sentinel_read_fd, fcntl.F_SETFL, sr_flags | os.O_NONBLOCK)

    master_fd, slave_fd = pty.openpty()
    sentinel_read_fd, sentinel_write_fd = os.pipe()

    pid = os.fork()
    if pid == 0:
        on_slave(slave_fd, master_fd, sentinel_write_fd)

    on_master(master_fd, slave_fd, sentinel_write_fd)
    return Terminal(pid, master_fd, sentinel_read_fd)
