import unittest

from matching_engine_core.engine_loader import PyOrderBook


class TestMatchingEngine(unittest.TestCase):
    def test_partial_fill_records_trade_and_resting_quantity(self):
        book = PyOrderBook()
        book.process_incoming(101, 10000, 5, 2)

        trades = book.process_incoming(202, 10000, 3, 1)

        self.assertEqual(
            trades,
            [{
                "maker_order_id": 101,
                "taker_order_id": 202,
                "price": 10000,
                "quantity": 3,
                "side": 1,
            }],
        )
        self.assertEqual(
            book.get_book_state()["asks"],
            [{"order_id": 101, "price": 10000, "quantity": 2}],
        )

    def test_match_uses_price_then_fifo_priority(self):
        book = PyOrderBook()
        book.process_incoming(101, 10000, 2, 2)
        book.process_incoming(102, 10000, 3, 2)
        book.process_incoming(103, 9900, 4, 2)

        trades = book.process_incoming(201, 10000, 9, 1)

        self.assertEqual(
            [
                (trade["maker_order_id"], trade["price"], trade["quantity"])
                for trade in trades
            ],
            [(103, 9900, 4), (101, 10000, 2), (102, 10000, 3)],
        )

    def test_non_crossing_order_produces_no_trades(self):
        book = PyOrderBook()
        book.process_incoming(101, 10100, 2, 2)

        self.assertEqual(
            book.process_incoming(202, 10000, 2, 1),
            [],
        )


if __name__ == "__main__":
    unittest.main()
