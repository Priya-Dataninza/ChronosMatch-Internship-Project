from src.mmap_ring_buffer import RingBuffer


def display_buffer_status(buffer):
    stats = buffer.get_stats()

    print("\n===== RING BUFFER MONITOR =====")
    print(f"Capacity       : {stats['capacity']}")
    print(f"Orders waiting : {stats['used']}")
    print(f"Free slots     : {stats['free']}")
    print(f"Usage           : {stats['usage_percent']}%")
    print(f"Read index      : {stats['read_index']}")
    print(f"Write index     : {stats['write_index']}")
    print("===============================\n")


if __name__ == "__main__":
    ring_buffer = RingBuffer(
        path="chronosmatch_ring_buffer.dat",
        capacity=1024
    )

    try:
        display_buffer_status(ring_buffer)
    finally:
        ring_buffer.close()
