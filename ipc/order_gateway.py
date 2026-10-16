# order_gateway.py
import time
from order_format import (
    init_ring_buffer, get_mmap_instance, HEADER_FORMAT, 
    HEADER_SIZE, ORDER_FORMAT, ORDER_SIZE, MAX_ORDERS
)

init_ring_buffer()
file_handle, shared_memory = get_mmap_instance(mode="r+b")

# --- UPDATED: Added side: int parameter ---
def produce_order(order_id: int, price: int, quantity: int, side: int) -> bool:
    write_ptr, read_ptr = HEADER_FORMAT.unpack(shared_memory[0:HEADER_SIZE])
    
    if write_ptr - read_ptr >= MAX_ORDERS:
        print("[CRITICAL] Buffer Overflow!")
        return False

    slot_index = write_ptr % MAX_ORDERS
    offset = HEADER_SIZE + (slot_index * ORDER_SIZE)
    
    # --- UPDATED: Packs 4 parameters now into the binary structure ---
    shared_memory[offset:offset + ORDER_SIZE] = ORDER_FORMAT.pack(order_id, price, quantity, side)
    
    # Advance the pointer and flush memory cache immediately to the kernel map
    new_write_ptr = write_ptr + 1
    shared_memory[0:HEADER_SIZE] = HEADER_FORMAT.pack(new_write_ptr, read_ptr)
    shared_memory.flush() 
    return True

if __name__ == "__main__":
    print("[GATEWAY] Active. Enter orders manually to test real-time pipeline.")
    # --- UPDATED: Format hint includes Side now ---
    print("Format: order_id price quantity side (e.g., 101 15000 5 1 for BUY or 102 15050 10 2 for SELL).")
    print("Type 'exit' to quit.\n")
    
    try:
        while True:
            user_input = input("New Order > ").strip()
            if user_input.lower() == 'exit':
                break
            
            try:
                # --- UPDATED: Unpacks 4 values from input ---
                oid, prc, qty, side = map(int, user_input.split())
                
                # --- FIXED: Corrected the side validation tuple check ---
                if side not in (1, 2):
                    print("Invalid side! Use 1 for BUY, 2 for SELL.")
                    continue
                    
                if produce_order(oid, prc, qty, side):
                    side_name = "BUY" if side == 1 else "SELL"
                    print(f" -> Sent {side_name} Order {oid} to ring buffer.")
            except ValueError:
                print("Invalid input format. Use numbers: order_id price quantity side")
    finally:
        shared_memory.close()
        file_handle.close()
