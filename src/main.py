import asyncio

from market_simulator import generate_orders
from mmap_ring_buffer import RingBuffer


async def main():
    ring_buffer = RingBuffer(
        path="chronosmatch_ring_buffer.dat",
        capacity=1024,
    )

    try:
        async for order in generate_orders(
            total_orders=10,
            delay=0.5,
        ):
            try:
                ring_buffer.write_order(order)
                print(
                    f"Order {order.order_id} sent to IPC ring buffer"
                )
            except BufferError:
                print("Ring buffer is full; order was not written.")
                break
    finally:
        ring_buffer.close()


if __name__ == "__main__":
    asyncio.run(main())

