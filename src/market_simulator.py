
import argparse
import asyncio
import random
import sys
from dataclasses import dataclass
from pathlib import Path
import time


PRICE_SCALE = 100

SIDE_TO_CODE = {
    "BUY": 1,
    "SELL": 2,
}


@dataclass
class Order:
    """Represents a simulated market order."""

    order_id: int
    side: str
    price: float
    quantity: int
    timestamp_ns: int


def convert_order_for_gateway(order: Order) -> tuple[int, int, int, int]:
    """Convert an order into the integer format used by the IPC gateway."""

    price_cents = round(order.price * PRICE_SCALE)
    side_code = SIDE_TO_CODE[order.side]

    return order.order_id, price_cents, order.quantity, side_code


def send_order_to_gateway(order: Order) -> bool:
    """Send an order to Member 1's IPC gateway."""

    project_root = Path(__file__).resolve().parent.parent
    ipc_dir = str(project_root / "ipc")

    if ipc_dir not in sys.path:
        sys.path.insert(0, ipc_dir)

    # Import the gateway only when sending an order.
    from order_gateway import produce_order

    order_id, price, quantity, side = convert_order_for_gateway(order)

    return produce_order(order_id, price, quantity, side)


async def generate_orders(total_orders: int = 10, delay: float = 0.5):
    """Generate mock market orders asynchronously."""

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

        if order_id < total_orders:
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

    try:
        async for order in generate_orders(args.orders, args.delay):
            try:
                sent = send_order_to_gateway(order)

                if sent:
                    print(
                        f"[GATEWAY] Order {order.order_id} "
                        "sent successfully."
                    )
                else:
                    print(
                        f"[GATEWAY] Order {order.order_id} "
                        "was rejected."
                    )

            except (ImportError, OSError) as error:
                print(f"[GATEWAY ERROR] {error}")
                break

    finally:
        # The gateway opens shared memory when first imported.
        # Close it after the simulator finishes.
        gateway = sys.modules.get("order_gateway")
        if gateway is not None:
            if hasattr(gateway, "shared_memory"):
                gateway.shared_memory.close()
            if hasattr(gateway, "file_handle"):
                gateway.file_handle.close()


if __name__ == "__main__":
    asyncio.run(main())
