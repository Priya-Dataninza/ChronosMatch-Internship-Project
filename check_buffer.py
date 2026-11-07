
from ipc.shared_buffer import (
    init_ring_buffer,
    get_mmap_instance,
    buffer_lock,
    HEADER_FORMAT,
    MAX_ORDERS,
)

def check_buffer():
    init_ring_buffer()
    file_handle, shared_memory = get_mmap_instance()

    try:
        with buffer_lock(file_handle):
            write_ptr, read_ptr = HEADER_FORMAT.unpack_from(
                shared_memory, 0
            )

            pending = write_ptr - read_ptr
            usage = (pending / MAX_ORDERS) * 100

            print("\n========== CHRONOSMATCH BUFFER STATUS ==========")

            print(f"Write pointer:     {write_ptr:,}")
            print(f"Read pointer:      {read_ptr:,}")
            print(f"Pending orders:    {pending:,}")
            print(f"Buffer capacity:   {MAX_ORDERS:,}")
            print(f"Buffer usage:      {usage:.2f}%")

            if pending == 0:
                print("\n[STATUS] Buffer is EMPTY.")

            elif pending == MAX_ORDERS:
                print("\n[STATUS] Buffer is FULL.")

            else:
                print("\n[STATUS] Buffer contains pending orders.")

            print("================================================")

    finally:
        shared_memory.close()
        file_handle.close()


if __name__ == "__main__":
    check_buffer()
