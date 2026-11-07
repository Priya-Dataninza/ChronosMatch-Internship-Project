
from matching_engine_core.order_book_fallback import PyOrderBook

book = PyOrderBook()

# First order: BUY 5 units at price 10000
book.process_incoming(101, 10000, 5, 1)

print("After BUY:")
print(book.get_book_state())

# Second order: SELL 3 units at price 10000
book.process_incoming(102, 10000, 3, 2)

print("\nAfter SELL:")
print(book.get_book_state())

print("\nSummary:")
print(book.get_book_summary())
