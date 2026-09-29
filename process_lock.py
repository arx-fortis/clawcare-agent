"""OS-released process locks for a trusted local ClawCare ledger."""
from contextlib import contextmanager
import os


class Busy(Exception):
    pass


@contextmanager
def process_lock(path):
    handle = open(path, 'a+b')
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b'0'); handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            raise Busy('Another process owns this ledger lock') from e
        yield
    finally:
        handle.close()
