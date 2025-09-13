import asyncio
import errno
import logging
import queue, threading
from typing import Generator, Tuple

from action.app.terminal import Terminal
from action.app.terminal_types import TerminalOutput

logger = logging.getLogger(__name__)


def read_pty(
    terminal: Terminal,
) -> Generator[TerminalOutput, None, None]:
    try:
        while True:
            output = terminal.read_blocking()
            yield output
            if output.output == b'':
                break

    except BaseException as e:
        logger.error(f"Error reading PTY", exc_info=True)
        yield TerminalOutput(
            is_done=False,
            output=None,
            error=str(e),
        )

def read_pty_into_queue(
    terminal: Terminal,
    output_queue: queue.Queue[TerminalOutput],
    loop: asyncio.AbstractEventLoop,
) -> None:
    try:
        for item in read_pty(terminal):
            # push each TerminalOutput into the asyncio queue
            loop.call_soon_threadsafe(output_queue.put, item)
    finally:
        # signal completion
        loop.call_soon_threadsafe(q.put_nowait, None)


class PtyReader:
    """
    One reader thread per PTY.
    - Calls terminal.read() in a loop (blocking).
    - Emits raw chunks into a Queue.
    - Emits None once on EOF to signal completion.
    """
    def __init__(self, terminal: Terminal, output_queue: queue.Queue[bytes | None]):
        self.terminal = terminal
        self.output_queue = output_queue
        self._t = threading.Thread(
            target=self._run, name=f"pty-reader-{terminal.terminal_fd}", daemon=True
        )
        self._stop = threading.Event()

    def start(self):
        self._t.start()

    def stop(self):
        # To stop immediately, close the master FD elsewhere; that will wake read() with EOF.
        self._stop.set()

    def get_chunk(self, timeout: float | None = None) -> bytes | None:
        """
        Blocks until the next chunk is available, or until timeout (raises queue.Empty).
        Returns None exactly once when EOF is reached.
        """
        return self.q.get(timeout=timeout)

    def _run(self):
        try:
            while not self._stop.is_set():
                chunk = self.terminal.read(self.chunk_size)  # blocks
                if chunk is None:            # EOF
                    self.q.put_nowait(None)   # signal completion
                    return
                self.q.put_nowait(chunk)
        except Exception:
            # You can push an error marker here if you want to propagate exceptions
            try:
                self.q.put_nowait(None)
            except Exception:
                pass
