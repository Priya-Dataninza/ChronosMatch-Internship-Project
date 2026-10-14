# order_gateway.py
from order_format import init_buffer, get_mmap_instance, ORDER_FORMAT

init_buffer()
file_handle, shared_memory = get_mmap_instance()

def accept_new_order(slot_index, order_id, price, quantity):
    """Call this whenever a network packet/order arrives."""
    offset = slot_index * ORDER_FORMAT.size
    
    # Pack parameters into your binary layout
    packed_data = ORDER_FORMAT.pack(order_id, price, quantity)
    
    # Direct memory copy (Ultra low latency)
    shared_memory[offset:offset + ORDER_FORMAT.size] = packed_data

# Example usage when a user submits an order:
accept_new_order(slot_index=0, order_id=101, price=15000, quantity=10)
