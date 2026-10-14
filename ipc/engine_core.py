# engine_core.py
import time
from order_format import get_mmap_instance, ORDER_FORMAT

file_handle, shared_memory = get_mmap_instance(mode="rb")

def match_loop():
    print("ChronosMatch Core Engine Active. Polling memory...")
    current_slot = 0
    
    while True:
        offset = current_slot * ORDER_FORMAT.size
        binary_chunk = shared_memory[offset:offset + ORDER_FORMAT.size]
        
        # Check if the slot is populated (Not all zeros)
        if binary_chunk != b'\x00' * ORDER_FORMAT.size:
            order_id, price, qty = ORDER_FORMAT.unpack(binary_chunk)
            
            print(f"[MATCH ENGINE] Processing Order ID: {order_id} | Price: {price/100} | Qty: {qty}")
            
            # --- YOUR MATCHING LOGIC GOES HERE (Orderbook cross) ---
            
            current_slot += 1  # Move to expect the next order chunk
        else:
            # Busy-wait or slight sleep if no new data has been written yet
            time.sleep(0.001) 

if __name__ == "__main__":
    match_loop()
