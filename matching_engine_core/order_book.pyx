# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: nonecheck=False
# cython: cdivision=True

from libc.stdlib cimport malloc, free
from libc.stdint cimport uint64_t, uint32_t, uint8_t
from time import perf_counter_ns


# 1 = BUY, 2 = SELL
cdef enum Side:
    BUY = 1
    SELL = 2


# Statically typed C struct for internal orders.
cdef struct Order:
    uint64_t order_id
    uint32_t price
    uint32_t qty
    uint8_t side
    Order* next
    Order* prev


# Each price level contains a FIFO doubly linked list of orders.
cdef struct PriceLevel:
    uint32_t price
    Order* head
    Order* tail
    PriceLevel* next
    PriceLevel* prev


# Bids and asks are maintained as separate sorted linked lists.
cdef struct OrderBook:
    PriceLevel* best_bid
    PriceLevel* best_ask
    uint64_t total_orders_processed


cdef inline Order* create_order(
    uint64_t order_id,
    uint32_t price,
    uint32_t qty,
    uint8_t side
) noexcept nogil:
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


cdef inline void insert_resting_order(
    PriceLevel* level,
    Order* ord
) noexcept nogil:
    # Append to the tail to preserve time priority (FIFO).
    ord.next = NULL
    ord.prev = level.tail

    if level.tail == NULL:
        level.head = ord
        level.tail = ord
    else:
        level.tail.next = ord
        level.tail = ord


cdef void add_resting_level_and_order(
    OrderBook* book,
    uint32_t price,
    Order* ord,
    uint8_t side
) noexcept nogil:
    cdef PriceLevel* level = <PriceLevel*>malloc(sizeof(PriceLevel))
    cdef PriceLevel* curr = NULL

    if level == NULL:
        free(ord)
        return

    level.price = price
    level.head = ord
    level.tail = ord
    level.next = NULL
    level.prev = NULL

    if side == BUY:
        # Bids: highest price first.
        if book.best_bid == NULL or price > book.best_bid.price:
            level.next = book.best_bid

            if book.best_bid != NULL:
                book.best_bid.prev = level

            book.best_bid = level
        else:
            curr = book.best_bid

            while curr.next != NULL and curr.next.price > price:
                curr = curr.next

            level.next = curr.next
            level.prev = curr

            if curr.next != NULL:
                curr.next.prev = level

            curr.next = level

    elif side == SELL:
        # Asks: lowest price first.
        if book.best_ask == NULL or price < book.best_ask.price:
            level.next = book.best_ask

            if book.best_ask != NULL:
                book.best_ask.prev = level

            book.best_ask = level
        else:
            curr = book.best_ask

            while curr.next != NULL and curr.next.price < price:
                curr = curr.next

            level.next = curr.next
            level.prev = curr

            if curr.next != NULL:
                curr.next.prev = level

            curr.next = level


cdef void match_order(
    OrderBook* book,
    uint64_t order_id,
    uint32_t price,
    uint32_t qty,
    uint8_t side
) noexcept nogil:
    cdef Order* new_ord = NULL
    cdef PriceLevel* current_level = NULL
    cdef Order* resting_ord = NULL
    cdef uint32_t match_qty = 0

    book.total_orders_processed += 1

    if side == BUY:
        # Incoming BUY matches the cheapest eligible asks first.
        current_level = book.best_ask

        while (
            current_level != NULL
            and current_level.price <= price
            and qty > 0
        ):
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

                free(current_level)
                current_level = book.best_ask
            else:
                break

    elif side == SELL:
        # Incoming SELL matches the highest eligible bids first.
        current_level = book.best_bid

        while (
            current_level != NULL
            and current_level.price >= price
            and qty > 0
        ):
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

                free(current_level)
                current_level = book.best_bid
            else:
                break

    # Any unfilled quantity becomes a resting limit order.
    if qty > 0:
        new_ord = create_order(order_id, price, qty, side)

        if new_ord == NULL:
            return

        if side == BUY:
            current_level = book.best_bid
        else:
            current_level = book.best_ask

        while current_level != NULL and current_level.price != price:
            current_level = current_level.next

        if current_level != NULL:
            insert_resting_order(current_level, new_ord)
        else:
            add_resting_level_and_order(book, price, new_ord, side)


cdef class PyOrderBook:
    cdef OrderBook* _book
    cdef uint64_t _last_start_ns
    cdef uint64_t _last_end_ns
    cdef uint64_t _last_latency_ns
    cdef uint64_t _total_latency_ns
    cdef uint64_t _max_latency_ns
    cdef uint64_t _latency_samples

    def __cinit__(self):
        self._book = <OrderBook*>malloc(sizeof(OrderBook))

        if self._book == NULL:
            raise MemoryError()

        # Initialize the book only after allocation succeeds.
        self._book.best_bid = NULL
        self._book.best_ask = NULL
        self._book.total_orders_processed = 0

        self._last_start_ns = 0
        self._last_end_ns = 0
        self._last_latency_ns = 0
        self._total_latency_ns = 0
        self._max_latency_ns = 0
        self._latency_samples = 0

    def __dealloc__(self):
        cdef PriceLevel* curr_level
        cdef PriceLevel* next_level
        cdef Order* curr_ord
        cdef Order* next_ord

        if self._book != NULL:
            # Free all bid levels and their orders.
            curr_level = self._book.best_bid

            while curr_level != NULL:
                next_level = curr_level.next
                curr_ord = curr_level.head

                while curr_ord != NULL:
                    next_ord = curr_ord.next
                    free(curr_ord)
                    curr_ord = next_ord

                free(curr_level)
                curr_level = next_level

            # Free all ask levels and their orders.
            curr_level = self._book.best_ask

            while curr_level != NULL:
                next_level = curr_level.next
                curr_ord = curr_level.head

                while curr_ord != NULL:
                    next_ord = curr_ord.next
                    free(curr_ord)
                    curr_ord = next_ord

                free(curr_level)
                curr_level = next_level

            free(self._book)
            self._book = NULL

    def process_incoming(
        self,
        uint64_t order_id,
        uint32_t price,
        uint32_t qty,
        uint8_t side
    ):
        if side not in (BUY, SELL):
            raise ValueError("side must be BUY (1) or SELL (2)")

        if price == 0 or qty == 0:
            raise ValueError("price and quantity must be positive")

        self._last_start_ns = perf_counter_ns()

        # The matching loop uses C structs and pointers without the GIL.
        with nogil:
            match_order(
                self._book,
                order_id,
                price,
                qty,
                side
            )

        self._last_end_ns = perf_counter_ns()

        self._last_latency_ns = (
            self._last_end_ns - self._last_start_ns
        )

        self._total_latency_ns += self._last_latency_ns
        self._latency_samples += 1

        if self._last_latency_ns > self._max_latency_ns:
            self._max_latency_ns = self._last_latency_ns

    @property
    def metrics(self):
        cdef uint64_t avg_latency = 0

        if self._latency_samples > 0:
            avg_latency = (
                self._total_latency_ns // self._latency_samples
            )

        return {
            "total_processed": self._book.total_orders_processed,
            "last_start_ns": self._last_start_ns,
            "last_end_ns": self._last_end_ns,
            "last_latency_ns": self._last_latency_ns,
            "total_latency_ns": self._total_latency_ns,
            "average_latency_ns": avg_latency,
            "max_latency_ns": self._max_latency_ns,
            "latency_samples": self._latency_samples,
        }

    def get_book_state(self):
        cdef PriceLevel* level
        cdef Order* order

        bids = []
        asks = []

        level = self._book.best_bid

        while level != NULL:
            order = level.head

            while order != NULL:
                bids.append({
                    "order_id": order.order_id,
                    "price": level.price,
                    "quantity": order.qty
                })
                order = order.next

            level = level.next

        level = self._book.best_ask

        while level != NULL:
            order = level.head

            while order != NULL:
                asks.append({
                    "order_id": order.order_id,
                    "price": level.price,
                    "quantity": order.qty
                })
                order = order.next

            level = level.next

        return {"bids": bids, "asks": asks}

    def get_book_summary(self):
        cdef PriceLevel* level
        cdef Order* order

        cdef uint64_t total_bid_qty = 0
        cdef uint64_t total_ask_qty = 0
        cdef uint64_t bid_order_count = 0
        cdef uint64_t ask_order_count = 0

        # Calculate BUY-side liquidity.
        level = self._book.best_bid

        while level != NULL:
            order = level.head

            while order != NULL:
                total_bid_qty += order.qty
                bid_order_count += 1
                order = order.next

            level = level.next

        # Calculate SELL-side liquidity.
        level = self._book.best_ask

        while level != NULL:
            order = level.head

            while order != NULL:
                total_ask_qty += order.qty
                ask_order_count += 1
                order = order.next

            level = level.next

        return {
            "total_bid_quantity": total_bid_qty,
            "total_ask_quantity": total_ask_qty,
            "bid_order_count": bid_order_count,
            "ask_order_count": ask_order_count
        }

    def get_market_imbalance(self):
        cdef PriceLevel* level
        cdef Order* order
        cdef uint64_t bid_qty = 0
        cdef uint64_t ask_qty = 0
        cdef uint64_t total_qty
        cdef double imbalance

        level = self._book.best_bid

        while level != NULL:
            order = level.head

            while order != NULL:
                bid_qty += order.qty
                order = order.next

            level = level.next

        level = self._book.best_ask

        while level != NULL:
            order = level.head

            while order != NULL:
                ask_qty += order.qty
                order = order.next

            level = level.next

        total_qty = bid_qty + ask_qty

        if total_qty == 0:
            return {
                "bid_quantity": bid_qty,
                "ask_quantity": ask_qty,
                "imbalance": 0.0,
                "pressure": "EMPTY"
            }

        # Cast before subtraction to avoid unsigned underflow.
        imbalance = (
            (<double>bid_qty - <double>ask_qty)
            / <double>total_qty
        )

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
            "pressure": pressure
        }


# Build from the project root:
# python setup.py build_ext --inplace --force
