# engine_core.py
import time
from order_format import (
    get_mmap_instance, HEADER_FORMAT, HEADER_SIZE, 
    ORDER_FORMAT, ORDER_SIZE, MAX_ORDERS
)

file_handle, shared_memory = get_mmap_instance(mode="r+b")

def run_engine():
    print("[ENGINE] ChronosMatch Core Online. Actively scanning memory matrix...\n")
    
    while True:
        write_ptr, read_ptr = HEADER_FORMAT.unpack(shared_memory[0:HEADER_SIZE])
        
        if write_ptr > read_ptr:
            slot_index = read_ptr % MAX_ORDERS
            offset = HEADER_SIZE + (slot_index * ORDER_SIZE)
            
            binary_chunk = shared_memory[offset:offset + ORDER_SIZE]
            
            if binary_chunk == b'\x00' * ORDER_SIZE:
                new_read_ptr = read_ptr + 1
                shared_memory[0:HEADER_SIZE] = HEADER_FORMAT.pack(write_ptr, new_read_ptr)
                continue
            
            # --- UPDATED: Unpacks 4 values now (added side) ---
            order_id, price, qty, side = ORDER_FORMAT.unpack(binary_chunk)
            
            # --- UPDATED: Human-readable Side label ---
            side_label = "BUY" if side == 1 else "SELL"
            print(f"[ENGINE] Parsed Slot [{slot_index}] -> ID: {order_id} | {side_label} | Price: ₹{price/100:.2f} | Qty: {qty}")
            
            # Wipe slot clean and update engine tracking pointers
            shared_memory[offset:offset + ORDER_SIZE] = b'\x00' * ORDER_SIZE
            new_read_ptr = read_ptr + 1
            shared_memory[0:HEADER_SIZE] = HEADER_FORMAT.pack(write_ptr, new_read_ptr)
            shared_memory.flush()
        else:
            # --- FIXED BUG: Changed 'break' to 'continue' so the engine stays alive waiting for data ---
            time.sleep(0.0001)
            continue

if __name__ == "__main__":
    try:
        run_engine()
    except KeyboardInterrupt:
        print("\n[ENGINE] Shutting down cleanly.")
    finally:
        shared_memory.close()
        file_handle.close()
