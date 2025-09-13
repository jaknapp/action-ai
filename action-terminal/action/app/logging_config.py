import logging
import os
import sys
import textwrap

try:
    from dotenv import load_dotenv, find_dotenv  # type: ignore
except Exception:  # pragma: no cover
    def load_dotenv(*args, **kwargs):  # type: ignore
        return False

    def find_dotenv(*args, **kwargs):  # type: ignore
        return ""


class WrapFormatter(logging.Formatter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._first_log = True
    
    def format(self, record: logging.LogRecord):
        msg = super().format(record)
        
        # Ensure first log message starts on a new line
        prefix = "\n" if self._first_log else ""
        self._first_log = False
        
        if len(msg) > 200:
            head = msg[:200] + "..."
            tail = "\n\t" + "\n\t".join(textwrap.wrap(record.message, 200))
            return f"{prefix}{head}\n{tail}\n"
        return f"{prefix}{msg}"
    

def init_logging_from_env() -> None:
    try:
        env_path = find_dotenv(usecwd=True)
        if env_path:
            load_dotenv(env_path)
    except Exception:
        pass

    log_format = os.environ.get("LOG_FORMAT", "%(levelname)s %(name)s: %(message)s").replace("\\t", "\t")
    level_name = os.environ.get("LOG_LEVEL", "INFO")
    level = logging._nameToLevel.get(level_name.upper(), logging.INFO)

    formatter = WrapFormatter(fmt=log_format)

    logger = logging.getLogger("action.app")
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.__stdout__)
    handler.setLevel(level)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
