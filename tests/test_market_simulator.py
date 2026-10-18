
import asyncio
import unittest

from src.market_simulator import (
    Order,
    convert_order_for_gateway,
    generate_orders,
)


class TestMarketSimulator(unittest.TestCase):

    def test_generates_requested_number_of_orders(self):
        async def run_test():
            orders = []

            async for order in generate_orders(
                total_orders=3,
                delay=0,
            ):
                orders.append(order)

            self.assertEqual(len(orders), 3)
            self.assertEqual(
                [order.order_id for order in orders],
                [1, 2, 3],
            )

        asyncio.run(run_test())

    def test_negative_delay_raises_error(self):
        async def run_test():
            with self.assertRaises(ValueError):
                async for _ in generate_orders(
                    total_orders=1,
                    delay=-0.1,
                ):
                    pass

        asyncio.run(run_test())

    def test_negative_total_orders_raises_error(self):
        async def run_test():
            with self.assertRaises(ValueError):
                async for _ in generate_orders(
                    total_orders=-1,
                    delay=0,
                ):
                    pass

        asyncio.run(run_test())

    def test_orders_have_valid_values(self):
        async def run_test():
            orders = []

            async for order in generate_orders(
                total_orders=5,
                delay=0,
            ):
                orders.append(order)

            for order in orders:
                self.assertIn(order.side, ["BUY", "SELL"])
                self.assertGreaterEqual(order.price, 95.0)
                self.assertLessEqual(order.price, 105.0)
                self.assertGreaterEqual(order.quantity, 1)
                self.assertLessEqual(order.quantity, 100)
                self.assertGreater(order.timestamp_ns, 0)

        asyncio.run(run_test())

    def test_zero_orders(self):
        async def run_test():
            orders = []

            async for order in generate_orders(
                total_orders=0,
                delay=0,
            ):
                orders.append(order)

            self.assertEqual(orders, [])

        asyncio.run(run_test())

    def test_converts_buy_order_for_gateway(self):
        order = Order(
            order_id=1,
            side="BUY",
            price=99.75,
            quantity=5,
            timestamp_ns=123,
        )

        result = convert_order_for_gateway(order)

        self.assertEqual(result, (1, 9975, 5, 1))

    def test_converts_sell_order_for_gateway(self):
        order = Order(
            order_id=2,
            side="SELL",
            price=90.80,
            quantity=10,
            timestamp_ns=456,
        )

        result = convert_order_for_gateway(order)

        self.assertEqual(result, (2, 9080, 10, 2))


if __name__ == "__main__":
    unittest.main()
