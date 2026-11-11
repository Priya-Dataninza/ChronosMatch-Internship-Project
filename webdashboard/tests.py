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
        self.assertContains(response, "Recent executions")
        self.assertContains(response, "AVG MATCH LATENCY")
        self.assertContains(response, 'id="engine-counts"')
        self.assertContains(response, "python manage.py runchronos")

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
        }

        response = self.client.get(reverse("webdashboard:status"))

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload["queue"]["queued"], 12)
        self.assertEqual(payload["trades"][0]["taker_order_id"], 2)
        self.assertEqual(payload["engine"]["average_latency_ns"], 3000)

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
            )

        self.assertEqual(response.status_code, 302)
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
