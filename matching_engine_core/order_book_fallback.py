
class PyOrderBook:
    """Pure-Python reference implementation of the Cython order book."""

    def __init__(self):
        self.bids = {}  # price -> FIFO list of orders
        self.asks = {}
        self.total_processed = 0

    def process_incoming(self, order_id, price, qty, side):
        if side not in (1, 2):
            raise ValueError("side must be BUY (1) or SELL (2)")

        if price <= 0 or qty <= 0:
            raise ValueError("price and quantity must be positive")

        self.total_processed += 1
        trades = []

        if side == 1:  # BUY matches the cheapest eligible asks
            while qty > 0 and self.asks:
                best_price = min(self.asks)

                if best_price > price:
                    break

                orders = self.asks[best_price]
                while qty > 0 and orders:
                    resting = orders[0]
                    matched = min(qty, resting["quantity"])

                    trades.append({
                        "maker_order_id": resting["order_id"],
                        "taker_order_id": order_id,
                        "price": best_price,
                        "quantity": matched,
                        "side": side,
                    })
                    qty -= matched
                    resting["quantity"] -= matched

                    if resting["quantity"] == 0:
                        orders.pop(0)

                if not orders:
                    del self.asks[best_price]

            if qty > 0:
                self.bids.setdefault(price, []).append({
                    "order_id": order_id,
                    "price": price,
                    "quantity": qty,
                })

        else:  # SELL matches the highest eligible bids
            while qty > 0 and self.bids:
                best_price = max(self.bids)

                if best_price < price:
                    break

                orders = self.bids[best_price]
                while qty > 0 and orders:
                    resting = orders[0]
                    matched = min(qty, resting["quantity"])

                    trades.append({
                        "maker_order_id": resting["order_id"],
                        "taker_order_id": order_id,
                        "price": best_price,
                        "quantity": matched,
                        "side": side,
                    })
                    qty -= matched
                    resting["quantity"] -= matched

                    if resting["quantity"] == 0:
                        orders.pop(0)

                if not orders:
                    del self.bids[best_price]

            if qty > 0:
                self.asks.setdefault(price, []).append({
                    "order_id": order_id,
                    "price": price,
                    "quantity": qty,
                })

        return trades

    @property
    def metrics(self):
        return {"total_processed": self.total_processed}

    def get_book_summary(self):
        bid_orders = [
            order
            for orders in self.bids.values()
            for order in orders
        ]
        ask_orders = [
            order
            for orders in self.asks.values()
            for order in orders
        ]
        return {
            "total_bid_quantity": sum(
                order["quantity"] for order in bid_orders
            ),
            "total_ask_quantity": sum(
                order["quantity"] for order in ask_orders
            ),
            "bid_order_count": len(bid_orders),
            "ask_order_count": len(ask_orders),
        }

    def get_market_imbalance(self):
        bid_qty = sum(
            order["quantity"]
            for orders in self.bids.values()
            for order in orders
        )
        ask_qty = sum(
            order["quantity"]
            for orders in self.asks.values()
            for order in orders
        )
        total_qty = bid_qty + ask_qty

        if total_qty == 0:
            return {
                "bid_quantity": bid_qty,
                "ask_quantity": ask_qty,
                "imbalance": 0.0,
                "pressure": "EMPTY",
            }

        imbalance = (bid_qty - ask_qty) / total_qty

        if imbalance > 0.2:
            pressure = "BUY PRESSURE"
        elif imbalance < -0.2:
            pressure = "SELL PRESSURE"
        else:
            pressure = "BALANCED"

        return {
            "bid_quantity": bid_qty,
            "ask_quantity": ask_qty,
            "imbalance": imbalance,
            "pressure": pressure,
        }

    def get_book_state(self):
        bids = []
        asks = []

        for price in sorted(self.bids, reverse=True):
            bids.extend(self.bids[price])

        for price in sorted(self.asks):
            asks.extend(self.asks[price])

        return {"bids": bids, "asks": asks}

    def get_market_depth(self):
        bids = [
            {
                "price": price,
                "quantity": sum(order["quantity"] for order in self.bids[price]),
                "order_count": len(self.bids[price]),
            }
            for price in sorted(self.bids, reverse=True)[:10]
        ]
        asks = [
            {
                "price": price,
                "quantity": sum(order["quantity"] for order in self.asks[price]),
                "order_count": len(self.asks[price]),
            }
            for price in sorted(self.asks)[:10]
        ]
        return {"bids": bids, "asks": asks}
