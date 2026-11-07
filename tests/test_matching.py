import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

    
from matching_engine_core.order_book_fallback import PyOrderBook

book = PyOrderBook()

# Add a SELL order: 5 units at price 10000
book.process_incoming(101, 10000, 5, 2)

# Add a BUY order: 3 units at price 10000
book.process_incoming(102, 10000, 3, 1)

state = book.get_book_state()

print("Metrics:", book.metrics)
print("Remaining orders:", state)

assert state["asks"] == [
    {"order_id": 101, "price": 10000, "quantity": 2}
]
assert state["bids"] == []

print("PASS: Matching and remaining quantity verified.")