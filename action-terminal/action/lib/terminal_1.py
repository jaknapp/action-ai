import fcntl
import os
import pty
import queue
import select
import signal
import struct
import termios
from typing import Tuple

from action.app.terminal_types import TerminalOutput


def write_all_to_fd(fd: int, data: bytes) -> None:
    """Write all bytes to a file descriptor."""
    view = memoryview(data)
    while view:
        n = os.write(fd, view)
        view = view[n:]


def fg_pgid(tty_fd: int) -> int:
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


class Terminal:



class Termina:

    def __init__(self, output_queue: queue.Queue[bytes], stop_mark: str):
        self.output_queue = output_queue
        self.stop_mark = stop_mark

        self.master_fd: int | None = None
        self.slave_fd: int | None = None
        self.sentinel_read_fd: int | None = None
        self.sentinel_write_fd: int | None = None

    def on_pre_fork(self) -> None:
        self.master_fd, self.slave_fd = pty.openpty()

        # Create sentinel pipes to know when the command prompt is ready
        self.sentinel_read_fd, self.sentinel_write_fd = os.pipe()

    def on_master(self) -> None:
        os.close(self.slave_fd)
        self.slave_fd = None

        os.close(self.sentinel_write_fd)
        self.sentinel_write_fd = None

        # Set master to non-blocking
        flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
        fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def on_pre_execve(self, env: dict[str, str]) -> None:
        env["PROMPT_COMMAND"] = 'printf "READY\n" >&$READY_FD || :'

        # Don't close sentinel fd when execve is called
        flags = fcntl.fcntl(self.sentinel_write_fd, fcntl.F_GETFD)
        fcntl.fcntl(self.sentinel_write_fd, fcntl.F_SETFD, flags & ~fcntl.FD_CLOEXEC)

        # Don't block writing in case the reader lets the buffer fill up
        # for whatever reason
        fl = fcntl.fcntl(self.sentinel_write_fd, fcntl.F_GETFL)
        fcntl.fcntl(self.sentinel_write_fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

    def on_slave(self) -> None:
        try:
            os.setsid()
            os.login_tty(self.slave_fd)

            try:
                os.close(self.master_fd)
                self.master_fd = None
            except OSError:
                pass

            try:
                os.close(self.sentinel_read_fd)
                self.sentinel_read_fd = None
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
                # Sentinel before prompt
                "PROMPT_COMMAND": 'printf "\\033]9;READY\\007"',
                "PROMPT_COMMAND": 'printf "READY\n" >&$READY_FD || :',
                "PS1": "cmd> ",
                "USER": os.environ["USER"],
                "LOGNAME": os.environ["LOGNAME"],
            }

            # Exec a single interactive bash; no profiles/rc for predictability
            os.execve("/bin/bash", ["bash", "--norc", "--noprofile", "-i"], terminal_env)

        finally:
            # Couldn't run execve
            os._exit(127)

    def start_terminal(self) -> None:
        """Start a terminal with PTY."""
        self.on_pre_fork()

        pid = os.fork()
        if pid == 0:
            self.on_slave()
        else:
            self.on_master()

    def poll(self) -> None:
        while True:
            try:
                r, _, _ = select.select(
                    [self.master_fd, self.sentinel_read_fd],  # rlist
                    [],  # wlist
                    [],  # xlist
                    None,  # timeout
                )
                self.ready_fds = r
                return
            except InterruptedError:
                # Some signal interrupted the select. Just try again.
                continue

    def read(self) -> bytes | None:
        if self.sentinel_read_fd in self.ready_fds:
            _ = os.read(self.sentinel_read_fd, 16384)
            is_done = True
        else:
            is_done = False

        if self.master_fd in self.ready_fds:
            read_bytes = os.read(self.master_fd, 16384)
        else:
            read_bytes = None
        
        terminal_output = TerminalOutput(
            is_done=is_done,
            stop_mark_found=False,
            output=read_bytes,
            error=None,
        )
        self.output_queue.put(terminal_output)

    def send_bytes(self, input_bytes: bytes) -> None:
        write_all_to_fd(fd=self.master_fd, data=input_bytes)

    def send_text(self, text: str) -> None:
        write_all_to_fd(fd=self.master_fd, data=text.encode("utf-8"))

    def send_signal(self, signal_param: int | str) -> None:
        if isinstance(signal_param, str):
            signal_int = getattr(signal, signal_param)
        else:
            signal_int = signal_param
        pg = fg_pgid(tty_fd=self.master_fd)
        os.killpg(pg, signal_int)
