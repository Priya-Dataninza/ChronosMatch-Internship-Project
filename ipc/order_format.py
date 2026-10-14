# shared_buffer.py
import mmap
import struct
import os

# 12-byte layout: ID (4B), Price (4B), Qty (4B)
ORDER_FORMAT = struct.Struct("<III")
MAX_ORDERS = 100000 
FILE_SIZE = ORDER_FORMAT.size * MAX_ORDERS
FILE_NAME = "shared.bin"

def init_buffer():
    """Run this once when starting your system to allocate disk space."""
    if not os.path.exists(FILE_NAME):
        with open(FILE_NAME, "wb") as f:
            f.truncate(FILE_SIZE)

def get_mmap_instance(mode="r+b"):
    """Returns an open file descriptor and mmap instance."""
    f = open(FILE_NAME, mode)
    mem = mmap.mmap(f.fileno(), FILE_SIZE, access=mmap.ACCESS_WRITE if "w" in mode or "+" in mode else mmap.ACCESS_READ)
    return f, mem
