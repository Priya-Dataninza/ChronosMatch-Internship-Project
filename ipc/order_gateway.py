# order_gateway.py
import time
from order_format import (
    init_ring_buffer, get_mmap_instance, HEADER_FORMAT, 
    HEADER_SIZE, ORDER_FORMAT, ORDER_SIZE, MAX_ORDERS
)

init_ring_buffer()
file_handle, shared_memory = get_mmap_instance(mode="r+b")

def produce_order(order_id: int, price: int, quantity: int) -> bool:
    write_ptr, read_ptr = HEADER_FORMAT.unpack(shared_memory[0:HEADER_SIZE])
    
    if write_ptr - read_ptr >= MAX_ORDERS:
        print("[CRITICAL] Buffer Overflow!")
        return False

    slot_index = write_ptr % MAX_ORDERS
    offset = HEADER_SIZE + (slot_index * ORDER_SIZE)
    
    # Write the order bytes
    shared_memory[offset:offset + ORDER_SIZE] = ORDER_FORMAT.pack(order_id, price, quantity)
    
    # Advance the pointer and flush memory cache immediately to the kernel map
    new_write_ptr = write_ptr + 1
    shared_memory[0:HEADER_SIZE] = HEADER_FORMAT.pack(new_write_ptr, read_ptr)
    shared_memory.flush() 
    return True

if __name__ == "__main__":
    print("[GATEWAY] Active. Enter orders manually to test real-time pipeline.")
    print("Format: order_id price quantity (e.g., 101 15000 5). Type 'exit' to quit.\n")
    
    try:
        while True:
            user_input = input("New Order > ").strip()
            if user_input.lower() == 'exit':
                break
            
            try:
                oid, prc, qty = map(int, user_input.split())
                if produce_order(oid, prc, qty):
                    print(f" -> Sent Order {oid} to ring buffer.")
            except ValueError:
                print("Invalid input format. Use numbers: order_id price quantity")
    finally:
        shared_memory.close()
        file_handle.close()
