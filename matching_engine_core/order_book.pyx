# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: nonecheck=False
# cython: cdivision=True

from libc.stdlib cimport malloc, realloc, free
from libc.stdint cimport uint64_t, uint32_t, uint8_t
from threading import Lock
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


cdef struct Trade:
    uint64_t maker_order_id
    uint64_t taker_order_id
    uint32_t price
    uint32_t quantity
    uint8_t side


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


cdef inline int append_trade(
    Trade** trades,
    uint64_t* capacity,
    uint64_t* count,
    uint64_t maker_order_id,
    uint64_t taker_order_id,
    uint32_t price,
    uint32_t quantity,
    uint8_t side
) noexcept nogil:
    cdef uint64_t new_capacity
    cdef Trade* new_trades

    if count[0] == capacity[0]:
        if capacity[0] == 0:
            new_capacity = 8
        else:
            new_capacity = capacity[0] * 2

        if new_capacity < capacity[0]:
            return 0

        new_trades = <Trade*>realloc(
            trades[0],
            new_capacity * sizeof(Trade)
        )

        if new_trades == NULL:
            return 0

        trades[0] = new_trades
        capacity[0] = new_capacity

    trades[0][count[0]].maker_order_id = maker_order_id
    trades[0][count[0]].taker_order_id = taker_order_id
    trades[0][count[0]].price = price
    trades[0][count[0]].quantity = quantity
    trades[0][count[0]].side = side
    count[0] += 1

    return 1


cdef int add_resting_level_and_order(
    OrderBook* book,
    uint32_t price,
    Order* ord,
    uint8_t side
) noexcept nogil:
    cdef PriceLevel* level = <PriceLevel*>malloc(sizeof(PriceLevel))
    cdef PriceLevel* curr = NULL

    if level == NULL:
        return 0

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

    return 1


cdef int match_order(
    OrderBook* book,
    uint64_t order_id,
    uint32_t price,
    uint32_t qty,
    uint8_t side,
    Trade** trades,
    uint64_t* trade_capacity,
    uint64_t* trade_count
) noexcept nogil:
    cdef Order* new_ord = NULL
    cdef PriceLevel* current_level = NULL
    cdef Order* resting_ord = NULL
    cdef uint32_t match_qty = 0

    trade_count[0] = 0
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

                if not append_trade(
                    trades,
                    trade_capacity,
                    trade_count,
                    resting_ord.order_id,
                    order_id,
                    current_level.price,
                    match_qty,
                    side
                ):
                    return 0

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

                if not append_trade(
                    trades,
                    trade_capacity,
                    trade_count,
                    resting_ord.order_id,
                    order_id,
                    current_level.price,
                    match_qty,
                    side
                ):
                    return 0

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
            return 0

        if side == BUY:
            current_level = book.best_bid
        else:
            current_level = book.best_ask

        while current_level != NULL and current_level.price != price:
            current_level = current_level.next

        if current_level != NULL:
            insert_resting_order(current_level, new_ord)
        else:
            if not add_resting_level_and_order(
                book, price, new_ord, side
            ):
                free(new_ord)
                return 0

    return 1


cdef class PyOrderBook:
    cdef OrderBook* _book
    cdef object _process_lock
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
        self._process_lock = Lock()

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
        cdef Trade* trade_buffer = NULL
        cdef uint64_t trade_capacity = 0
        cdef uint64_t trade_count = 0
        cdef uint64_t trade_index
        cdef int success
        trades = []

        if side not in (BUY, SELL):
            raise ValueError("side must be BUY (1) or SELL (2)")

        if price == 0 or qty == 0:
            raise ValueError("price and quantity must be positive")

        with self._process_lock:
            self._last_start_ns = perf_counter_ns()

            with nogil:
                success = match_order(
                    self._book,
                    order_id,
                    price,
                    qty,
                    side,
                    &trade_buffer,
                    &trade_capacity,
                    &trade_count
                )

            self._last_end_ns = perf_counter_ns()
            self._last_latency_ns = (
                self._last_end_ns - self._last_start_ns
            )
            self._total_latency_ns += self._last_latency_ns
            self._latency_samples += 1

            if self._last_latency_ns > self._max_latency_ns:
                self._max_latency_ns = self._last_latency_ns

            if not success:
                if trade_buffer != NULL:
                    free(trade_buffer)
                raise MemoryError("Unable to store the resting order")

            try:
                for trade_index in range(trade_count):
                    trades.append({
                        "maker_order_id": (
                            trade_buffer[trade_index].maker_order_id
                        ),
                        "taker_order_id": (
                            trade_buffer[trade_index].taker_order_id
                        ),
                        "price": trade_buffer[trade_index].price,
                        "quantity": (
                            trade_buffer[trade_index].quantity
                        ),
                        "side": trade_buffer[trade_index].side,
                    })
            finally:
                if trade_buffer != NULL:
                    free(trade_buffer)

        return trades

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

    def get_market_depth(self):
        cdef PriceLevel* level
        cdef Order* order
        cdef uint64_t quantity
        cdef uint64_t order_count
        cdef int depth
        bids = []
        asks = []

        level = self._book.best_bid
        depth = 0
        while level != NULL and depth < 10:
            quantity = 0
            order_count = 0
            order = level.head
            while order != NULL:
                quantity += order.qty
                order_count += 1
                order = order.next
            bids.append({
                "price": level.price,
                "quantity": quantity,
                "order_count": order_count
            })
            depth += 1
            level = level.next

        level = self._book.best_ask
        depth = 0
        while level != NULL and depth < 10:
            quantity = 0
            order_count = 0
            order = level.head
            while order != NULL:
                quantity += order.qty
                order_count += 1
                order = order.next
            asks.append({
                "price": level.price,
                "quantity": quantity,
                "order_count": order_count
            })
            depth += 1
            level = level.next

        return {"bids": bids, "asks": asks}


# Build from the project root:
# python setup.py build_ext --inplace --force
