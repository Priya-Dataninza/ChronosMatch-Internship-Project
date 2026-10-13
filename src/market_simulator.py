
import asyncio
import random
import time
from dataclasses import dataclass


@dataclass
class Order:
    order_id: int
    side: str
    price: float
    quantity: int
    timestamp_ns: int


async def generate_orders(total_orders: int = 10, delay: float = 0.5):
    """Generate simulated market orders asynchronously."""
    if total_orders < 0:
        raise ValueError("total_orders cannot be negative")

    if delay < 0:
        raise ValueError("delay cannot be negative")

    for order_id in range(1, total_orders + 1):
        order = Order(
            order_id=order_id,
            side=random.choice(["BUY", "SELL"]),
            price=round(random.uniform(95.0, 105.0), 2),
            quantity=random.randint(1, 100),
            timestamp_ns=time.perf_counter_ns(),
        )

        print(
            f"Order {order.order_id}: "
            f"{order.side} | "
            f"Price: {order.price:.2f} | "
            f"Quantity: {order.quantity} | "
            f"Timestamp: {order.timestamp_ns}"
        )

        yield order

        if order_id < total_orders:
            await asyncio.sleep(delay)


async def main():
    async for order in generate_orders():
        # For now, display each order.
        # Later, connect this to the team's matching engine.
        pass


if __name__ == "__main__":
    asyncio.run(main())
