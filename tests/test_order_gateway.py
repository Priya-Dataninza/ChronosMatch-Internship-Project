
import importlib
import struct
import sys
import unittest
from types import ModuleType
from unittest.mock import Mock, patch


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

        # Import the gateway with mocked dependencies.
        # This prevents tests from modifying the real shared.bin.
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

        # Set write pointer to 5 and read pointer to 2.
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


if __name__ == "__main__":
    unittest.main()
