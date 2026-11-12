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

    def test_market_depth_aggregates_and_orders_price_levels(self):
        book = PyOrderBook()
        book.process_incoming(101, 10000, 2, 1)
        book.process_incoming(102, 10000, 3, 1)
        book.process_incoming(103, 9900, 4, 1)
        book.process_incoming(201, 10100, 5, 2)
        book.process_incoming(202, 10200, 6, 2)

        self.assertEqual(
            book.get_market_depth(),
            {
                "bids": [
                    {"price": 10000, "quantity": 5, "order_count": 2},
                    {"price": 9900, "quantity": 4, "order_count": 1},
                ],
                "asks": [
                    {"price": 10100, "quantity": 5, "order_count": 1},
                    {"price": 10200, "quantity": 6, "order_count": 1},
                ],
            },
        )

    def test_market_depth_returns_only_the_best_ten_levels(self):
        book = PyOrderBook()
        for index in range(11):
            price = 10000 + index * 100
            book.process_incoming(index + 1, price, 1, 1)

        bids = book.get_market_depth()["bids"]

        self.assertEqual(len(bids), 10)
        self.assertEqual(bids[0]["price"], 11000)
        self.assertEqual(bids[-1]["price"], 10100)

    def test_book_summary_counts_all_orders_and_remaining_quantities(self):
        book = PyOrderBook()
        book.process_incoming(101, 10000, 5, 1)
        book.process_incoming(102, 10000, 3, 1)
        book.process_incoming(201, 10100, 4, 2)

        summary = book.get_book_summary()

        self.assertEqual(
            summary,
            {
                "total_bid_quantity": 8,
                "total_ask_quantity": 4,
                "bid_order_count": 2,
                "ask_order_count": 1,
            },
        )

    def test_book_summary_includes_levels_beyond_display_depth(self):
        book = PyOrderBook()
        for index in range(11):
            book.process_incoming(index + 1, 10000 + index, index + 1, 1)

        self.assertEqual(len(book.get_market_depth()["bids"]), 10)
        self.assertEqual(
            book.get_book_summary(),
            {
                "total_bid_quantity": sum(range(1, 12)),
                "total_ask_quantity": 0,
                "bid_order_count": 11,
                "ask_order_count": 0,
            },
        )


if __name__ == "__main__":
    unittest.main()
