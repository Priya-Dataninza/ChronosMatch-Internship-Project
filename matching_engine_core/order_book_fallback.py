
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

        if side == 1:  # BUY matches the cheapest eligible asks
            while qty > 0 and self.asks:
                best_price = min(self.asks)

                if best_price > price:
                    break

                orders = self.asks[best_price]
                while qty > 0 and orders:
                    resting = orders[0]
                    matched = min(qty, resting["quantity"])

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

    @property
    def metrics(self):
        return {"total_processed": self.total_processed}

    def get_book_state(self):
        bids = []
        asks = []

        for price in sorted(self.bids, reverse=True):
            bids.extend(self.bids[price])

        for price in sorted(self.asks):
            asks.extend(self.asks[price])

        return {"bids": bids, "asks": asks}
