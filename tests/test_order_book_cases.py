import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
    
from matching_engine_core.order_book_fallback import PyOrderBook


def test_full_match():
    book = PyOrderBook()

    book.process_incoming(1, 10000, 5, 2)  # SELL 5
    book.process_incoming(2, 10000, 5, 1)  # BUY 5

    state = book.get_book_state()

    assert state["bids"] == []
    assert state["asks"] == []
    print("PASS: Full match")


def test_price_priority():
    book = PyOrderBook()

    book.process_incoming(1, 10000, 5, 2)  # SELL at 10000
    book.process_incoming(2, 10100, 5, 2)  # SELL at 10100
    book.process_incoming(3, 10100, 5, 1)  # BUY at 10100

    state = book.get_book_state()

    # The cheaper SELL should be filled first.
    assert state["asks"] == [
        {"order_id": 2, "price": 10100, "quantity": 5}
    ]
    assert state["bids"] == []
    print("PASS: Price priority")


def test_time_priority():
    book = PyOrderBook()

    book.process_incoming(1, 10000, 3, 2)  # Earlier SELL
    book.process_incoming(2, 10000, 4, 2)  # Later SELL
    book.process_incoming(3, 10000, 4, 1)  # BUY 4

    state = book.get_book_state()

    # Earlier SELL should fill first; later SELL supplies the last unit.
    assert state["asks"] == [
        {"order_id": 2, "price": 10000, "quantity": 3}
    ]
    assert state["bids"] == []
    print("PASS: Time priority")


def test_non_crossing_orders():
    book = PyOrderBook()

    book.process_incoming(1, 10100, 5, 2)  # SELL at 10100
    book.process_incoming(2, 10000, 3, 1)  # BUY at 10000

    state = book.get_book_state()

    assert state["asks"] == [
        {"order_id": 1, "price": 10100, "quantity": 5}
    ]
    assert state["bids"] == [
        {"order_id": 2, "price": 10000, "quantity": 3}
    ]
    print("PASS: Non-crossing orders")


if __name__ == "__main__":
    test_full_match()
    test_price_priority()
    test_time_priority()
    test_non_crossing_orders()
    print("\nAll order-book tests passed!")