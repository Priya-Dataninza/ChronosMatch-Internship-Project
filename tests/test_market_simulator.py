
import unittest
from unittest.mock import AsyncMock, patch

from src.market_simulator import generate_orders


class TestMarketSimulator(unittest.IsolatedAsyncioTestCase):

    async def test_generates_requested_number_of_orders(self):
        with patch(
            "src.market_simulator.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            orders = [
                order
                async for order in generate_orders(
                    total_orders=3, delay=0
                )
            ]

        self.assertEqual(len(orders), 3)
        self.assertEqual(
            [order.order_id for order in orders],
            [1, 2, 3],
        )

    async def test_orders_have_valid_values(self):
        with patch(
            "src.market_simulator.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            orders = [
                order
                async for order in generate_orders(
                    total_orders=5, delay=0
                )
            ]

        for order in orders:
            self.assertIn(order.side, ["BUY", "SELL"])
            self.assertGreaterEqual(order.price, 95.0)
            self.assertLessEqual(order.price, 105.0)
            self.assertGreaterEqual(order.quantity, 1)
            self.assertLessEqual(order.quantity, 100)

    async def test_zero_orders(self):
        orders = [
            order
            async for order in generate_orders(
                total_orders=0, delay=0
            )
        ]

        self.assertEqual(orders, [])


if __name__ == "__main__":
    unittest.main()
