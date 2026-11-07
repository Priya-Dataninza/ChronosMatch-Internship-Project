import os
import tempfile
import unittest
from types import SimpleNamespace

from src.mmap_ring_buffer import RingBuffer


class TestRingBuffer(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(
            self.temp_dir.name,
            "test_ring_buffer.dat",
        )
        self.buffer = RingBuffer(
            path=self.path,
            capacity=2,
        )

    def tearDown(self):
        self.buffer.close()
        self.temp_dir.cleanup()

    def make_order(
        self,
        order_id=1,
        side="BUY",
        price=100.5,
        quantity=10,
        timestamp_ns=123456789,
    ):
        return SimpleNamespace(
            order_id=order_id,
            side=side,
            price=price,
            quantity=quantity,
            timestamp_ns=timestamp_ns,
        )

    def test_write_and_read_order(self):
        order = self.make_order()
        self.buffer.write_order(order)

        result = self.buffer.read_order()

        self.assertIsNotNone(result)
        self.assertEqual(result.order_id, order.order_id)
        self.assertEqual(result.side, order.side)
        self.assertAlmostEqual(result.price, order.price)
        self.assertEqual(result.quantity, order.quantity)
        self.assertEqual(result.timestamp_ns, order.timestamp_ns)

    def test_empty_buffer_returns_none(self):
        self.assertIsNone(self.buffer.read_order())

    def test_full_buffer_raises_error(self):
        self.buffer.write_order(self.make_order(order_id=1))
        self.buffer.write_order(self.make_order(order_id=2))

        with self.assertRaises(BufferError):
            self.buffer.write_order(self.make_order(order_id=3))

    def test_invalid_side_raises_error(self):
        with self.assertRaises(ValueError):
            self.buffer.write_order(
                self.make_order(side="HOLD")
            )

    def test_buffer_can_be_reused_after_read(self):
        self.buffer.write_order(self.make_order(order_id=1))
        self.buffer.write_order(self.make_order(order_id=2))

        self.buffer.read_order()

        self.buffer.write_order(self.make_order(order_id=3))

        self.assertEqual(self.buffer.read_order().order_id, 2)
        self.assertEqual(self.buffer.read_order().order_id, 3)


if __name__ == "__main__":
    unittest.main()
