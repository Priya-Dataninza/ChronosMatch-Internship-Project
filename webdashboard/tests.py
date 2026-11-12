import json
import os
import sys
from types import ModuleType
from unittest.mock import Mock, patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webapp.settings")

import django
from django.apps import apps

if not apps.ready:
    django.setup()

from django.test import Client, SimpleTestCase
from django.urls import reverse


class DashboardViewsTests(SimpleTestCase):
    def setUp(self):
        self.client = Client()

    @patch("webdashboard.views._queue_status")
    @patch("webdashboard.views._recent_trades")
    def test_dashboard_renders_frontend(self, recent_trades, queue_status):
        response = self.client.get(reverse("webdashboard:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Engine overview")
        self.assertContains(response, "Submit an order")
        self.assertContains(response, "Live order book")
        self.assertContains(response, 'id="bids-body"')
        self.assertContains(response, "Recent executions")
        self.assertContains(response, "AVG MATCH LATENCY")
        self.assertContains(response, "PROCESSING RATE")
        self.assertContains(response, 'id="orders-per-second"')
        self.assertContains(response, 'id="engine-counts"')
        self.assertContains(response, "Queue 200-order demo")
        self.assertContains(response, 'id="latency-chart"')
        self.assertContains(response, 'id="bid-order-count"')
        self.assertContains(response, 'id="ask-order-count"')
        self.assertContains(response, "python manage.py runchronos")
        self.assertContains(response, 'data-status-url="/api/status/"')

    @patch("webdashboard.views._queue_status")
    @patch("webdashboard.views._recent_trades")
    @patch("webdashboard.views.read_engine_status")
    def test_status_endpoint_returns_live_data_shape(
        self, engine_status, recent_trades, queue_status
    ):
        queue_status.return_value = {
            "capacity": 1_000_000,
            "queued": 12,
            "free": 999_988,
            "usage_percent": 0.0,
            "status": "online",
        }
        recent_trades.return_value = [{
            "maker_order_id": 1,
            "taker_order_id": 2,
            "price": 100.0,
            "quantity": 4,
            "side": "BUY",
            "executed_at": "2026-11-07 10:00:00",
        }]
        engine_status.return_value = {
            "status": "running",
            "engine_type": "cython",
            "orders_processed": 23,
            "trades_executed": 4,
            "last_latency_ns": 2000,
            "average_latency_ns": 3000,
            "max_latency_ns": 5000,
            "order_book": {
                "bids": [{"price": 10000, "quantity": 4, "order_count": 1}],
                "asks": [],
                "summary": {
                    "total_bid_quantity": 4,
                    "total_ask_quantity": 0,
                    "bid_order_count": 1,
                    "ask_order_count": 0,
                },
            },
        }

        response = self.client.get(reverse("webdashboard:status"))

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload["queue"]["queued"], 12)
        self.assertEqual(payload["trades"][0]["taker_order_id"], 2)
        self.assertEqual(payload["engine"]["average_latency_ns"], 3000)
        self.assertEqual(
            payload["engine"]["order_book"]["bids"][0]["price"],
            10000,
        )
        self.assertEqual(
            payload["engine"]["order_book"]["summary"]["bid_order_count"],
            1,
        )
        self.assertFalse(payload["engine_managed"])

    @patch("webdashboard.views.read_engine_status")
    @patch("webdashboard.views.start_engine")
    def test_engine_on_endpoint_starts_engine(self, start_engine, engine_status):
        start_engine.return_value = {"started": True, "pid": 1234}
        engine_status.return_value = {"status": "running", "pid": 1234}

        response = self.client.post(reverse("webdashboard:engine_on"))

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload["engine"]["status"], "running")
        start_engine.assert_called_once_with()

    @patch("webdashboard.views.read_engine_status")
    @patch("webdashboard.views.stop_engine")
    def test_engine_off_endpoint_stops_engine(self, stop_engine, engine_status):
        stop_engine.return_value = {"stopped": True}
        engine_status.return_value = {"status": "stopped"}

        response = self.client.post(reverse("webdashboard:engine_off"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["engine"]["status"], "stopped")
        stop_engine.assert_called_once_with()

    @patch("webdashboard.views.read_engine_status")
    def test_bulk_demo_requires_running_engine(self, engine_status):
        engine_status.return_value = {"status": "stopped"}
        gateway = ModuleType("ipc.order_gateway")
        gateway.produce_orders = Mock(return_value=True)

        with patch.dict(sys.modules, {"ipc.order_gateway": gateway}):
            response = self.client.post(reverse("webdashboard:simulate_bulk"))

        self.assertEqual(response.status_code, 409)
        gateway.produce_orders.assert_not_called()

    @patch("webdashboard.views.read_engine_status")
    def test_bulk_demo_queues_two_hundred_crossing_orders(self, engine_status):
        engine_status.return_value = {
            "status": "running",
            "order_book": {
                "bids": [{"price": 10000}],
                "asks": [{"price": 10200}],
            },
        }
        gateway = ModuleType("ipc.order_gateway")
        gateway.produce_orders = Mock(return_value=True)

        with patch.dict(sys.modules, {"ipc.order_gateway": gateway}):
            response = self.client.post(reverse("webdashboard:simulate_bulk"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            json.loads(response.content)["orders_submitted"],
            200,
        )
        batch = gateway.produce_orders.call_args.args[0]
        self.assertEqual(len(batch), 200)
        self.assertEqual(len({order[0] for order in batch}), 200)
        for buy, sell in zip(batch[::2], batch[1::2]):
            self.assertEqual((buy[3], sell[3]), (1, 2))
            self.assertGreater(buy[1], sell[1])

    def test_submit_order_uses_existing_gateway(self):
        gateway = ModuleType("ipc.order_gateway")
        gateway.produce_order = Mock(return_value=True)

        with patch.dict(sys.modules, {"ipc.order_gateway": gateway}):
            response = self.client.post(
                reverse("webdashboard:submit_order"),
                {
                    "order_id": "51",
                    "price": "101.25",
                    "quantity": "7",
                    "side": "SELL",
                },
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Any unfilled quantity will appear")
        self.assertContains(response, "Live order book")
        gateway.produce_order.assert_called_once_with(51, 10125, 7, 2)

    def test_submit_order_rejects_invalid_side_before_gateway(self):
        gateway = ModuleType("ipc.order_gateway")
        gateway.produce_order = Mock(return_value=True)

        with patch.dict(sys.modules, {"ipc.order_gateway": gateway}):
            response = self.client.post(
                reverse("webdashboard:submit_order"),
                {
                    "order_id": "51",
                    "price": "101.25",
                    "quantity": "7",
                    "side": "HOLD",
                },
            )

        self.assertEqual(response.status_code, 302)
        gateway.produce_order.assert_not_called()
