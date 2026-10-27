
import mmap
import os
import struct
from contextlib import contextmanager

HEADER_FORMAT = struct.Struct("<QQ")
HEADER_SIZE = HEADER_FORMAT.size

ORDER_FORMAT = struct.Struct("<IIII")
ORDER_SIZE = ORDER_FORMAT.size

MAX_ORDERS = 100000 # Use 2 for initial tests; later change to 100_000.
FILE_SIZE = HEADER_SIZE + ORDER_SIZE * MAX_ORDERS
FILE_NAME = "shared.bin"


def init_ring_buffer():
    """Create the buffer if it doesn't exist; never reset an existing buffer."""
    if not os.path.exists(FILE_NAME):
        with open(FILE_NAME, "w+b") as f:
            f.truncate(FILE_SIZE)
            f.write(HEADER_FORMAT.pack(0, 0))
        print("[SYSTEM] Ring buffer initialized.")

    if os.path.getsize(FILE_NAME) != FILE_SIZE:
        raise RuntimeError(
            f"{FILE_NAME} has an unexpected size. "
            "Stop both processes and reset the buffer."
        )


def get_mmap_instance(mode="r+b"):
    f = open(FILE_NAME, mode)

    try:
        access = (
            mmap.ACCESS_WRITE
            if "+" in mode or "w" in mode
            else mmap.ACCESS_READ
        )

        if os.name == "nt":
            mem = mmap.mmap(
                f.fileno(), FILE_SIZE,
                access=access,
                tagname="chronosmatch_mmap",
            )
        else:
            mem = mmap.mmap(
                f.fileno(), FILE_SIZE,
                access=access,
            )

        return f, mem

    except Exception:
        f.close()
        raise


@contextmanager
def buffer_lock(file_handle):
    """Exclusive lock shared by processes opening the same file."""
    if os.name == "nt":
        import msvcrt

        file_handle.seek(0)
        msvcrt.locking(file_handle.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            file_handle.seek(0)
            msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)


def reset_ring_buffer():
    """Reset only when the producer and consumer are both stopped."""
    init_ring_buffer()

    file_handle, mem = get_mmap_instance()

    try:
        with buffer_lock(file_handle):
            mem[:] = b"\x00" * FILE_SIZE
            HEADER_FORMAT.pack_into(mem, 0, 0, 0)
            mem.flush()
    finally:
        mem.close()
        file_handle.close()


if __name__ == "__main__":
    import sys

    init_ring_buffer()

    if "--reset" in sys.argv:
        reset_ring_buffer()
        print("[SYSTEM] Ring buffer reset.")
