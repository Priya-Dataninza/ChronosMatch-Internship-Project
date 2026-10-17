
import argparse
import asyncio
import random
import time
from dataclasses import dataclass


@dataclass
class Order:
    """Represents a simulated market order."""

    order_id: int
    side: str
    price: float
    quantity: int
    timestamp_ns: int


async def generate_orders(total_orders: int = 10, delay: float = 0.5):
    """Generate mock market orders asynchronously.

    Args:
        total_orders: Number of orders to generate.
        delay: Delay between orders in seconds.

    Yields:
        Order: A generated market order.

    Raises:
        ValueError: If total_orders or delay is negative.
    """
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
            f"Order {order.order_id}: {order.side} | "
            f"Price: {order.price:.2f} | "
            f"Quantity: {order.quantity} | "
            f"Timestamp: {order.timestamp_ns}"
        )

        yield order

        await asyncio.sleep(delay)


async def main():
    """Run the market simulator from the command line."""
    parser = argparse.ArgumentParser(
        description="ChronosMatch market simulator"
    )

    parser.add_argument(
        "--orders",
        type=int,
        default=10,
        help="Number of orders to generate (default: 10)",
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between orders in seconds (default: 0.5)",
    )

    args = parser.parse_args()

    if args.orders < 0:
        parser.error("--orders cannot be negative")

    if args.delay < 0:
        parser.error("--delay cannot be negative")

    async for _ in generate_orders(args.orders, args.delay):
        pass


if __name__ == "__main__":
    asyncio.run(main())
