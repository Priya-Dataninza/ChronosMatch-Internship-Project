
from ipc.shared_buffer import (
    init_ring_buffer,
    get_mmap_instance,
    buffer_lock,
    HEADER_FORMAT,
    HEADER_SIZE,
    ORDER_FORMAT,
    ORDER_SIZE,
    MAX_ORDERS,
)

MAX_UINT32 = (1 << 32) - 1

init_ring_buffer()
file_handle, shared_memory = get_mmap_instance()


def order_id_exists(order_id: int, write_ptr: int, read_ptr: int) -> bool:
    """
    Check whether an order ID already exists
    among orders waiting in the ring buffer.
    """
    for pointer in range(read_ptr, write_ptr):
        slot_index = pointer % MAX_ORDERS
        offset = HEADER_SIZE + (slot_index * ORDER_SIZE)

        existing_order = ORDER_FORMAT.unpack_from(
            shared_memory, offset
        )

        if existing_order[0] == order_id:
            return True

    return False


def produce_order(
    order_id: int,
    price: int,
    quantity: int,
    side: int,
) -> bool:

    # Validate integer fields.
    values = (order_id, price, quantity, side)

    if not all(
        isinstance(value, int) and not isinstance(value, bool)
        and 0 <= value <= MAX_UINT32
        for value in values
    ):
        print("[REJECTED] Fields must be unsigned 32-bit integers.")
        return False

    if price == 0:
        print("[REJECTED] Price must be positive.")
        return False

    if quantity == 0:
        print("[REJECTED] Quantity must be positive.")
        return False

    if side not in (1, 2):
        print("[REJECTED] Side must be 1 (BUY) or 2 (SELL).")
        return False

    # Synchronize access to shared memory.
    with buffer_lock(file_handle):

        write_ptr, read_ptr = HEADER_FORMAT.unpack_from(
            shared_memory, 0
        )

        # Prevent duplicate pending order IDs.
        if order_id_exists(order_id, write_ptr, read_ptr):
            print(f"[REJECTED] Duplicate Order ID #{order_id}.")
            return False

        # Prevent buffer overflow.
        if write_ptr - read_ptr >= MAX_ORDERS:
            print("[BUFFER FULL] Order not written.")
            return False

        # Calculate the ring-buffer slot.
        slot_index = write_ptr % MAX_ORDERS
        offset = HEADER_SIZE + slot_index * ORDER_SIZE

        # Write the order directly into shared memory.
        ORDER_FORMAT.pack_into(
            shared_memory,
            offset,
            order_id,
            price,
            quantity,
            side,
        )

        # Publish the updated write pointer.
        HEADER_FORMAT.pack_into(
            shared_memory,
            0,
            write_ptr + 1,
            read_ptr,
        )

        shared_memory.flush()

    return True


if __name__ == "__main__":

    print("[GATEWAY] ChronosMatch producer ready.")
    print("Format: order_id price quantity side")
    print("Example: 101 15000 5 1 (BUY)")
    print("Type 'exit' to quit.\n")

    try:
        while True:
            user_input = input("New Order > ").strip()

            if user_input.lower() == "exit":
                break

            try:
                oid, price, qty, side = map(
                    int, user_input.split()
                )

                if produce_order(oid, price, qty, side):
                    label = "BUY" if side == 1 else "SELL"
                    print(f"[SENT] {label} order {oid}")

            except ValueError:
                print(
                    "Enter four integers: "
                    "order_id price quantity side"
                )

    except KeyboardInterrupt:
        print("\n[GATEWAY] Stopping.")

    finally:
        shared_memory.close()
        file_handle.close()
