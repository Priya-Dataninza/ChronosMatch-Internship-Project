import sqlite3
from pathlib import Path

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from ipc.shared_buffer import (
    HEADER_FORMAT,
    MAX_ORDERS,
    buffer_lock,
    get_mmap_instance,
    init_ring_buffer,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = PROJECT_ROOT / "ledger.db"


def _queue_status():
    init_ring_buffer()
    file_handle, memory = get_mmap_instance()
    try:
        with buffer_lock(file_handle):
            write_pointer, read_pointer = HEADER_FORMAT.unpack_from(
                memory, 0
            )
        pending = write_pointer - read_pointer
        if not 0 <= pending <= MAX_ORDERS:
            raise ValueError("Shared queue pointers are inconsistent")
        return {
            "capacity": MAX_ORDERS,
            "queued": pending,
            "free": MAX_ORDERS - pending,
            "usage_percent": round(pending / MAX_ORDERS * 100, 2),
            "status": "online",
        }
    finally:
        memory.close()
        file_handle.close()


def _recent_trades():
    if not LEDGER_PATH.exists():
        return []

    connection = sqlite3.connect(LEDGER_PATH, timeout=1)
    connection.row_factory = sqlite3.Row
    try:
        table_exists = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'executed_trades'"
        ).fetchone()
        if table_exists is None:
            return []

        rows = connection.execute(
            "SELECT maker_order_id, taker_order_id, price, quantity, "
            "side, executed_at FROM executed_trades "
            "ORDER BY rowid DESC LIMIT 8"
        ).fetchall()
        return [
            {
                "maker_order_id": row["maker_order_id"],
                "taker_order_id": row["taker_order_id"],
                "price": row["price"] / 100,
                "quantity": row["quantity"],
                "side": "BUY" if row["side"] == 1 else "SELL",
                "executed_at": row["executed_at"],
            }
            for row in rows
        ]
    finally:
        connection.close()


def dashboard(request):
    return render(request, "webdashboard/dashboard.html")


@require_GET
def status(request):
    try:
        queue_status = _queue_status()
    except (OSError, ValueError) as error:
        return JsonResponse(
            {"status": "unavailable", "error": str(error)},
            status=503,
        )

    try:
        trades = _recent_trades()
        ledger_status = "online" if LEDGER_PATH.exists() else "waiting"
    except sqlite3.Error as error:
        return JsonResponse(
            {
                "status": "partial",
                "queue": queue_status,
                "ledger_status": "unavailable",
                "error": f"Trade ledger unavailable: {error}",
            },
            status=503,
        )

    return JsonResponse({
        "status": "online",
        "queue": queue_status,
        "ledger_status": ledger_status,
        "trades": trades,
    })


@require_POST
def submit_order(request):
    try:
        order_id = int(request.POST.get("order_id", ""))
        price_cents = round(float(request.POST.get("price", "")) * 100)
        quantity = int(request.POST.get("quantity", ""))
        side_label = request.POST.get("side", "").upper()
    except (TypeError, ValueError, OverflowError):
        messages.error(request, "Enter a valid order ID, price, and quantity.")
        return redirect("webdashboard:dashboard")

    if side_label not in {"BUY", "SELL"}:
        messages.error(request, "Choose BUY or SELL.")
        return redirect("webdashboard:dashboard")

    try:
        from ipc.order_gateway import produce_order

        accepted = produce_order(
            order_id,
            price_cents,
            quantity,
            1 if side_label == "BUY" else 2,
        )
    except (OSError, ValueError) as error:
        messages.error(request, f"Could not submit order: {error}")
        return redirect("webdashboard:dashboard")

    if accepted:
        messages.success(
            request,
            f"{side_label} order #{order_id} queued successfully.",
        )
    else:
        messages.error(
            request,
            "Order rejected. Check the ID, price, quantity, and queue capacity.",
        )
    return redirect("webdashboard:dashboard")
