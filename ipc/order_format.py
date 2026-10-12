import mmap
import struct

# Define the binary format of one order
# I = unsigned 4-byte integer
ORDER_FORMAT = struct.Struct("<III")

# Example order
order_id = 101
price = 10000  # ₹100.00
quantity = 5

# Convert the order into bytes
order_bytes = ORDER_FORMAT.pack(
    order_id,
    price,
    quantity
)

print("Packed order:", order_bytes)
print("Order size:", len(order_bytes), "bytes")

# Create a file and reserve enough space for one order
with open("shared.bin", "w+b") as file:
    file.write(b"\x00" * ORDER_FORMAT.size)
    file.flush()

    # Map the file into memory
    with mmap.mmap(
        file.fileno(),
        ORDER_FORMAT.size,
        access=mmap.ACCESS_WRITE
    ) as memory:

        # Write the order bytes into mapped memory
        memory[:ORDER_FORMAT.size] = order_bytes

        print("Bytes written to mmap.")

        # Read the order back from mapped memory
        received_order = ORDER_FORMAT.unpack(
            memory[:ORDER_FORMAT.size]
        )

        received_id, received_price, received_quantity = received_order

        print("\nOrder read from mmap:")
        print("Order ID:", received_id)
        print("Price: ₹", received_price / 100)
        print("Quantity:", received_quantity)