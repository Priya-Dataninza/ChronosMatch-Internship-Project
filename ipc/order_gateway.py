
# order_gateway.py
from order_format import (
    init_ring_buffer,
    get_mmap_instance,
    HEADER_FORMAT,
    HEADER_SIZE,
    ORDER_FORMAT,
    ORDER_SIZE,
    MAX_ORDERS,
)

init_ring_buffer()
file_handle, shared_memory = get_mmap_instance(mode="r+b")


def produce_order(
    order_id: int,
    price: int,
    quantity: int,
    side: int,
) -> bool:
    # Validate order ID before packing unsigned integers.
    if order_id < 0:
        print(
            f"[REJECTED] Invalid Order #{order_id}: "
            "Order ID must be non-negative."
        )
        return False

    # Validate price and quantity.
    if price <= 0 or quantity <= 0:
        print(
            f"[REJECTED] Invalid Order #{order_id}: "
            "Price and Quantity must be greater than 0."
        )
        return False

    # Validate order side: 1 = BUY, 2 = SELL.
    if side not in (1, 2):
        print(
            f"[REJECTED] Invalid Order #{order_id}: "
            "Side must be 1 (BUY) or 2 (SELL)."
        )
        return False

    # Read the ring-buffer pointers.
    write_ptr, read_ptr = HEADER_FORMAT.unpack(
        shared_memory[0:HEADER_SIZE]
    )

    # Prevent buffer overflow.
    if write_ptr - read_ptr >= MAX_ORDERS:
        print("[CRITICAL] Buffer Overflow!")
        return False

    # Calculate the slot for the new order.
    slot_index = write_ptr % MAX_ORDERS
    offset = HEADER_SIZE + (slot_index * ORDER_SIZE)

    # Pack and write the order.
    shared_memory[offset:offset + ORDER_SIZE] = ORDER_FORMAT.pack(
        order_id,
        price,
        quantity,
        side,
    )

    # Advance the write pointer and flush shared memory.
    new_write_ptr = write_ptr + 1
    shared_memory[0:HEADER_SIZE] = HEADER_FORMAT.pack(
        new_write_ptr,
        read_ptr,
    )
    shared_memory.flush()

    return True


if __name__ == "__main__":
    print("[GATEWAY] Active. Enter orders manually to test real-time pipeline.")
    print(
        "Format: order_id price quantity side "
        "(e.g., 101 15000 5 1 for BUY or 102 15050 10 2 for SELL)."
    )
    print("Type 'exit' to quit.\n")

    try:
        while True:
            user_input = input("New Order > ").strip()

            if user_input.lower() == "exit":
                break

            try:
                oid, prc, qty, side = map(int, user_input.split())

                if side not in (1, 2):
                    print("Invalid side! Use 1 for BUY, 2 for SELL.")
                    continue

                if produce_order(oid, prc, qty, side):
                    side_name = "BUY" if side == 1 else "SELL"
                    print(
                        f" -> Sent {side_name} Order {oid} "
                        "to ring buffer."
                    )

            except ValueError:
                print(
                    "Invalid input format. "
                    "Use numbers: order_id price quantity side"
                )

    finally:
        shared_memory.close()
        file_handle.close()
