Can start a PTY with the following configuration options
- Environment variables
- Shell
- Window size

For now, we only support
- A fixed environment
- The bash shell
- 24x80 window size

We add special support for prompt detection during the set up of the terminal
We add support for stop mark detection when reading from the terminal


Quick shutdown recipe (faithful to a tty)
Close the master → triggers SIGHUP to fg pgid.

Poll waitpid(pid, WNOHANG) briefly; if still alive, send SIGTERM → wait → SIGKILL.

Final waitpid(pid, 0) to reap.

def reap_one(pid):
    try:
        return os.waitpid(pid, os.WNOHANG)  # (pid, status) or (0,0)
    # No child error
    except ChildProcessError:
        return (0,0)

import fcntl, termios, struct, os, signal

def fg_pgid(master_fd) -> int:
    buf = fcntl.ioctl(master_fd, termios.TIOCGPGRP, struct.pack("i", 0))
    return struct.unpack("i", buf)[0]

def send_sigint_like_ctrl_c(master_fd):
    try:
        os.killpg(fg_pgid(master_fd), signal.SIGINT)
    # Race condition - fg process ended
    except ProcessLookupError:
        pass  