
import importlib
import struct
import sys
import unittest

from types import ModuleType
from unittest.mock import Mock, patch
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "ipc")
)


class FakeSharedMemory(bytearray):
    def flush(self):
        pass


class TestOrderGateway(unittest.TestCase):

    def setUp(self):
        # Create an isolated ring buffer for testing.
        header_format = struct.Struct("<QQ")
        order_format = struct.Struct("<IIII")
        max_orders = 4

        self.memory = FakeSharedMemory(
            header_format.size + order_format.size * max_orders
        )
        self.file_handle = Mock()

        fake_format = ModuleType("order_format")
        fake_format.HEADER_FORMAT = header_format
        fake_format.HEADER_SIZE = header_format.size
        fake_format.ORDER_FORMAT = order_format
        fake_format.ORDER_SIZE = order_format.size
        fake_format.MAX_ORDERS = max_orders
        fake_format.init_ring_buffer = Mock()
        fake_format.get_mmap_instance = Mock(
            return_value=(self.file_handle, self.memory)
        )

        # Prevent tests from modifying the real shared.bin file.
        sys.modules.pop("order_gateway", None)

        with patch.dict(
            sys.modules,
            {"order_format": fake_format},
        ):
            self.gateway = importlib.import_module("order_gateway")

    def tearDown(self):
        sys.modules.pop("order_gateway", None)

    def test_rejects_invalid_sides(self):
        for side in (0, 3, -1):
            with self.subTest(side=side):
                result = self.gateway.produce_order(
                    order_id=1,
                    price=10000,
                    quantity=5,
                    side=side,
                )
                self.assertFalse(result)

    def test_invalid_side_does_not_advance_write_pointer(self):
        header_format = self.gateway.HEADER_FORMAT

        self.memory[:self.gateway.HEADER_SIZE] = (
            header_format.pack(5, 2)
        )

        result = self.gateway.produce_order(
            order_id=10,
            price=10000,
            quantity=5,
            side=3,
        )

        write_ptr, read_ptr = header_format.unpack(
            self.memory[:self.gateway.HEADER_SIZE]
        )

        self.assertFalse(result)
        self.assertEqual(write_ptr, 5)
        self.assertEqual(read_ptr, 2)

    def test_rejects_negative_order_id(self):
        result = self.gateway.produce_order(
            order_id=-1,
            price=10000,
            quantity=5,
            side=1,
        )

        self.assertFalse(result)

    def test_negative_order_id_does_not_advance_write_pointer(self):
        header_format = self.gateway.HEADER_FORMAT

        self.memory[:self.gateway.HEADER_SIZE] = (
            header_format.pack(5, 2)
        )

        result = self.gateway.produce_order(
            order_id=-1,
            price=10000,
            quantity=5,
            side=1,
        )

        write_ptr, read_ptr = header_format.unpack(
            self.memory[:self.gateway.HEADER_SIZE]
        )

        self.assertFalse(result)
        self.assertEqual(write_ptr, 5)
        self.assertEqual(read_ptr, 2)

    def test_rejects_numeric_fields_above_uint32_limit(self):
        max_value = (1 << 32) - 1

        invalid_orders = [
            {
                "order_id": max_value + 1,
                "price": 100,
                "quantity": 1,
                "side": 1,
            },
            {
                "order_id": 1,
                "price": max_value + 1,
                "quantity": 1,
                "side": 1,
            },
            {
                "order_id": 1,
                "price": 100,
                "quantity": max_value + 1,
                "side": 1,
            },
        ]

        for order in invalid_orders:
            with self.subTest(order=order):
                result = self.gateway.produce_order(**order)
                self.assertFalse(result)

    def test_accepts_uint32_boundary_values(self):
        max_value = (1 << 32) - 1

        result = self.gateway.produce_order(
            order_id=max_value,
            price=max_value,
            quantity=max_value,
            side=2,
        )

        self.assertTrue(result)

        order_offset = self.gateway.HEADER_SIZE
        stored_order = self.gateway.ORDER_FORMAT.unpack(
            self.memory[
                order_offset:order_offset + self.gateway.ORDER_SIZE
            ]
        )

        self.assertEqual(
            stored_order,
            (max_value, max_value, max_value, 2),
        )

    def test_invalid_price_does_not_advance_write_pointer(self):
        header_format = self.gateway.HEADER_FORMAT

        self.memory[:self.gateway.HEADER_SIZE] = (
            header_format.pack(5, 2)
        )

        result = self.gateway.produce_order(
            order_id=10,
            price=0,
            quantity=5,
            side=1,
        )

        write_ptr, read_ptr = header_format.unpack(
            self.memory[:self.gateway.HEADER_SIZE]
        )

        self.assertFalse(result)
        self.assertEqual(write_ptr, 5)
        self.assertEqual(read_ptr, 2)

    def test_invalid_quantity_does_not_advance_write_pointer(self):
        header_format = self.gateway.HEADER_FORMAT

        self.memory[:self.gateway.HEADER_SIZE] = (
            header_format.pack(5, 2)
        )

        result = self.gateway.produce_order(
            order_id=10,
            price=10000,
            quantity=0,
            side=1,
        )

        write_ptr, read_ptr = header_format.unpack(
            self.memory[:self.gateway.HEADER_SIZE]
        )

        self.assertFalse(result)
        self.assertEqual(write_ptr, 5)
        self.assertEqual(read_ptr, 2)

    # New tests for duplicate order ID protection.

    def test_accepts_first_order_id(self):
        result = self.gateway.produce_order(
            order_id=101,
            price=10000,
            quantity=5,
            side=1,
        )

        self.assertTrue(result)

    def test_rejects_duplicate_pending_order_id(self):
        first_result = self.gateway.produce_order(
            order_id=101,
            price=10000,
            quantity=5,
            side=1,
        )

        second_result = self.gateway.produce_order(
            order_id=101,
            price=10100,
            quantity=3,
            side=2,
        )

        self.assertTrue(first_result)
        self.assertFalse(second_result)

    def test_accepts_different_order_ids(self):
        first_result = self.gateway.produce_order(
            order_id=101,
            price=10000,
            quantity=5,
            side=1,
        )

        second_result = self.gateway.produce_order(
            order_id=102,
            price=10100,
            quantity=3,
            side=2,
        )

        self.assertTrue(first_result)
        self.assertTrue(second_result)


if __name__ == "__main__":
    unittest.main()
