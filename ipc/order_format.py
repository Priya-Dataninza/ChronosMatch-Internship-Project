# shared_buffer.py
import mmap
import struct
import os

HEADER_FORMAT = struct.Struct("<QQ") 
HEADER_SIZE = HEADER_FORMAT.size

# --- CHANGE IS HERE: Added one extra 'I' for the side (Buy/Sell) ---
# Old: "<III" (order_id, price, quantity)
# New: "<IIII" (order_id, price, quantity, side)
ORDER_FORMAT = struct.Struct("<IIII")
ORDER_SIZE = ORDER_FORMAT.size

MAX_ORDERS = 100000  
FILE_SIZE = HEADER_SIZE + (ORDER_SIZE * MAX_ORDERS)
FILE_NAME = "shared.bin"

def init_ring_buffer():
    if not os.path.exists(FILE_NAME):
        with open(FILE_NAME, "wb") as f:
            f.truncate(FILE_SIZE)
            # Pre-pack empty head and tail
            f.seek(0)
            f.write(HEADER_FORMAT.pack(0, 0))
        print(f"[SYSTEM] Ring buffer file initialized.")

def get_mmap_instance(mode="r+b"):
    f = open(FILE_NAME, mode)
    is_write = "w" in mode or "+" in mode
    
    mem = mmap.mmap(
        f.fileno(), 
        FILE_SIZE, 
        access=mmap.ACCESS_WRITE if is_write else mmap.ACCESS_READ,
        tagname="chronosmatch_mmap"
    )
    return f, mem
