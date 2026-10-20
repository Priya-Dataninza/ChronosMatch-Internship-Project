# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: nonecheck=False
# cython: cdivision=True

from libc.stdlib cimport malloc, free
from libc.stdint cimport uint64_t, uint32_t, uint8_t

# 1 = BUY, 2 = SELL
cdef enum Side:
    BUY = 1
    SELL = 2

# Statically typed C struct for internal Orders
cdef struct Order:
    uint64_t order_id
    uint32_t price
    uint32_t qty
    uint8_t side
    Order* next
    Order* prev

# Statically typed C struct for a Price Level (Queue of Orders)
cdef struct PriceLevel:
    uint32_t price
    Order* head
    Order* tail
    PriceLevel* next
    PriceLevel* prev

# The core Order Book structure
cdef struct OrderBook:
    PriceLevel* best_bid
    PriceLevel* best_ask
    uint64_t total_orders_processed  # Small addition to track engine throughput

# Internal helper to create a new order node in memory
cdef inline Order* create_order(uint64_t order_id, uint32_t price, uint32_t qty, uint8_t side) noexcept nogil:
    cdef Order* ord = <Order*>malloc(sizeof(Order))
    if ord == NULL:
        return NULL
    ord.order_id = order_id
    ord.price = price
    ord.qty = qty
    ord.side = side
    ord.next = NULL
    ord.prev = NULL
    return ord

# Core matching engine loop running entirely WITHOUT the GIL
cdef void match_order(OrderBook* book, uint64_t order_id, uint32_t price, uint32_t qty, uint8_t side) noexcept nogil:
    cdef Order* new_ord = NULL
    cdef PriceLevel* current_level = NULL
    cdef Order* resting_ord = NULL
    cdef uint32_t match_qty = 0

    # Increment metric safely without the GIL
    book.total_orders_processed += 1

    if side == BUY:
        current_level = book.best_ask
        while current_level != NULL and current_level.price <= price and qty > 0:
            resting_ord = current_level.head
            while resting_ord != NULL and qty > 0:
                if qty < resting_ord.qty:
                    match_qty = qty
                else:
                    match_qty = resting_ord.qty
                
                qty -= match_qty
                resting_ord.qty -= match_qty
                
                if resting_ord.qty == 0:
                    current_level.head = resting_ord.next
                    if current_level.head != NULL:
                        current_level.head.prev = NULL
                    else:
                        current_level.tail = NULL
                    
                    free(resting_ord)
                    resting_ord = current_level.head
                else:
                    break
            
            if current_level.head == NULL:
                book.best_ask = current_level.next
                if book.best_ask != NULL:
                    book.best_ask.prev = NULL
                current_level = book.best_ask
            else:
                break

    elif side == SELL:
        current_level = book.best_bid
        while current_level != NULL and current_level.price >= price and qty > 0:
            resting_ord = current_level.head
            while resting_ord != NULL and qty > 0:
                if qty < resting_ord.qty:
                    match_qty = qty
                else:
                    match_qty = resting_ord.qty
                
                qty -= match_qty
                resting_ord.qty -= match_qty
                
                if resting_ord.qty == 0:
                    current_level.head = resting_ord.next
                    if current_level.head != NULL:
                        current_level.head.prev = NULL
                    else:
                        current_level.tail = NULL
                    free(resting_ord)
                    resting_ord = current_level.head
                else:
                    break
            
            if current_level.head == NULL:
                book.best_bid = current_level.next
                if book.best_bid != NULL:
                    book.best_bid.prev = NULL
                current_level = book.best_bid
            else:
                break

# Python Wrapper exposed to your Ring Buffer processor
cdef class PyOrderBook:
    cdef OrderBook* _book
    
    def __cinit__(self):
        self._book = <OrderBook*>malloc(sizeof(OrderBook))
        self._book.best_bid = NULL
        self._book.best_ask = NULL
        self._book.total_orders_processed = 0
        
    def __dealloc__(self):
        if self._book != NULL:
            free(self._book)

    def process_incoming(self, uint64_t order_id, uint32_t price, uint32_t qty, uint8_t side):
        with nogil:
            match_order(self._book, order_id, price, qty, side)

    # Exposed property to check metrics from Python code later
    @property
    def metrics(self):
        return {"total_processed": self._book.total_orders_processed}
