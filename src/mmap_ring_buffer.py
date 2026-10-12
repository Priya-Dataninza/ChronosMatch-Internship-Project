import mmap
import os
import struct
from contextlib import contextmanager
from dataclasses import dataclass


HEADER_FORMAT = "!4sIIII"
ORDER_FORMAT = "!QcdIQ"

HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
ORDER_SIZE = struct.calcsize(ORDER_FORMAT)
MAGIC = b"CMRB"


@dataclass
class OrderRecord:
    order_id: int
    side: str
    price: float
    quantity: int
    timestamp_ns: int


class RingBuffer:
    def __init__(self, path="chronosmatch_ring_buffer.dat",
                 capacity=1024):
        if capacity < 1:
            raise ValueError("Capacity must be positive")

        self.path = path
        self.lock_path = path + ".lock"
        self.capacity = capacity
        self.lock_file = open(self.lock_path, "a+b")

        try:
            with self._locked():
                expected_size = HEADER_SIZE + capacity * ORDER_SIZE

                with open(self.path, "a+b") as data_file:
                    data_file.seek(0, os.SEEK_END)
                    file_size = data_file.tell()

                    if file_size == 0:
                        data_file.truncate(expected_size)
                        data_file.flush()

                        with mmap.mmap(
                            data_file.fileno(), expected_size
                        ) as mapped:
                            mapped[:HEADER_SIZE] = struct.pack(
                                HEADER_FORMAT,
                                MAGIC, capacity, 0, 0, 0
                            )
                            mapped.flush()

                    actual_size = os.path.getsize(self.path)

                    if actual_size < HEADER_SIZE:
                        raise ValueError("Invalid ring buffer file")

                    with mmap.mmap(
                        data_file.fileno(), actual_size
                    ) as mapped:
                        magic, stored_capacity, _, _, _ = (
                            struct.unpack_from(HEADER_FORMAT, mapped, 0)
                        )

                    if magic != MAGIC:
                        raise ValueError("Invalid ring buffer header")

                    if stored_capacity != capacity:
                        raise ValueError(
                            f"Existing buffer capacity is "
                            f"{stored_capacity}, not {capacity}"
                        )

                    if actual_size != (
                        HEADER_SIZE + stored_capacity * ORDER_SIZE
                    ):
                        raise ValueError("Invalid ring buffer size")

            self.data_file = open(self.path, "r+b")
            self.memory = mmap.mmap(self.data_file.fileno(), 0)

        except Exception:
            self.lock_file.close()
            raise

    @contextmanager
    def _locked(self):
        if os.name == "nt":
            import msvcrt

            self.lock_file.seek(0, os.SEEK_END)
            if self.lock_file.tell() == 0:
                self.lock_file.write(b"\0")
                self.lock_file.flush()

            self.lock_file.seek(0)
            msvcrt.locking(
                self.lock_file.fileno(), msvcrt.LK_LOCK, 1
            )
            try:
                yield
            finally:
                self.lock_file.seek(0)
                msvcrt.locking(
                    self.lock_file.fileno(), msvcrt.LK_UNLCK, 1
                )
        else:
            import fcntl

            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)

    def _header(self):
        magic, capacity, read_idx, write_idx, count = (
            struct.unpack_from(HEADER_FORMAT, self.memory, 0)
        )

        if magic != MAGIC or capacity != self.capacity:
            raise ValueError("Ring buffer header is corrupted")

        if not (
            0 <= read_idx < capacity
            and 0 <= write_idx < capacity
            and 0 <= count <= capacity
        ):
            raise ValueError("Ring buffer indexes are corrupted")

        return read_idx, write_idx, count

    def write_order(self, order):
        side = order.side.upper()

        if side not in ("BUY", "SELL"):
            raise ValueError("Side must be BUY or SELL")

        if not 0 < order.order_id < 2**64:
            raise ValueError("Invalid order ID")

        if not 0 < order.quantity < 2**32:
            raise ValueError("Invalid quantity")

        if not 0 <= order.price < float("inf"):
            raise ValueError("Invalid price")

        if not 0 <= order.timestamp_ns < 2**64:
            raise ValueError("Invalid timestamp")

        side_byte = b"B" if side == "BUY" else b"S"

        with self._locked():
            read_idx, write_idx, count = self._header()

            if count == self.capacity:
                raise BufferError("Ring buffer is full")

            offset = HEADER_SIZE + write_idx * ORDER_SIZE

            struct.pack_into(
                ORDER_FORMAT,
                self.memory,
                offset,
                order.order_id,
                side_byte,
                order.price,
                order.quantity,
                order.timestamp_ns,
            )

            write_idx = (write_idx + 1) % self.capacity
            count += 1

            struct.pack_into(
                HEADER_FORMAT,
                self.memory,
                0,
                MAGIC,
                self.capacity,
                read_idx,
                write_idx,
                count,
            )

    def read_order(self):
        with self._locked():
            read_idx, write_idx, count = self._header()

            if count == 0:
                return None

            offset = HEADER_SIZE + read_idx * ORDER_SIZE

            (
                order_id,
                side_byte,
                price,
                quantity,
                timestamp_ns,
            ) = struct.unpack_from(ORDER_FORMAT, self.memory, offset)

            if side_byte not in (b"B", b"S"):
                raise ValueError("Invalid order side in buffer")

            read_idx = (read_idx + 1) % self.capacity
            count -= 1

            struct.pack_into(
                HEADER_FORMAT,
                self.memory,
                0,
                MAGIC,
                self.capacity,
                read_idx,
                write_idx,
                count,
            )

            return OrderRecord(
                order_id=order_id,
                side="BUY" if side_byte == b"B" else "SELL",
                price=price,
                quantity=quantity,
                timestamp_ns=timestamp_ns,
            )

    def close(self):
        if hasattr(self, "memory"):
            self.memory.close()
        if hasattr(self, "data_file"):
            self.data_file.close()
        if not self.lock_file.closed:
            self.lock_file.close()
