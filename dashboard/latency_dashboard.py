import curses
import os
import queue
import random
import sqlite3
import sys
import time
from collections import deque
from multiprocessing import Event, Process, Queue
from pathlib import Path
 
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
 
PRICE_SCALE = 100  # the simulator sends price x 100 (99.75 -> 9975)
WHALE_QTY = 90     # simulator quantities are 1-100, so 90+ counts as a whale
BUY, SELL = 1, 2
 
 
# ---------- 1. SQLite ledger (separate process) ----------
def ledger_writer(q, db_path="ledger.db"):
    """Saves every processed order. Gets whole batches, so it is fast."""
    con = sqlite3.connect(db_path)
    con.execute(
        "CREATE TABLE IF NOT EXISTS orders("
        "order_id INTEGER, side INTEGER, price INTEGER, "
        "qty INTEGER, latency_ns INTEGER)"
    )
    while True:
        batch = q.get()
        if batch is None:  # stop signal
            break
        con.executemany("INSERT INTO orders VALUES (?,?,?,?,?)", batch)
        con.commit()
    con.close()
 
 
# ---------- 2. Latency statistics ----------
class LatencyStats:
    def __init__(self, size=10000):
        self.values = deque(maxlen=size)  # last N latencies in ns
 
    def add(self, ns):
        self.values.append(ns)
 
    def summary_us(self):
        if not self.values:
            return 0.0, 0.0, 0.0
        data = sorted(self.values)
        avg = sum(data) / len(data) / 1000
        p99 = data[int(len(data) * 0.99) - 1 if len(data) > 100 else -1] / 1000
        return avg, p99, data[-1] / 1000
 
 
# ---------- 3. Workers: they produce the numbers ----------
# Every worker sends a message about every 0.1 s:
#   {"orders": [(order_id, side, price, qty, latency_ns), ...],
#    "processed": total so far, "backlog": orders waiting in the buffer,
#    "book": (best_bid, best_ask, number_of_bids, number_of_asks)}
def summarize_book(book):
    try:
        state = book.get_book_state()
    except AttributeError:  # engine version without get_book_state
        return None, None, 0, 0
    bids, asks = state["bids"], state["asks"]
    best_bid = max((o["price"] for o in bids), default=None)
    best_ask = min((o["price"] for o in asks), default=None)
    return best_bid, best_ask, len(bids), len(asks)
 
 
def engine_worker(out_q, stop):
    """LIVE: read orders from shared.bin, send them to the real engine, time each."""
    # The engine still has a printf() that would wreck the curses screen.
    # Send this process's C-level output to NUL. (Ask the team to remove printf.)
    os.dup2(os.open(os.devnull, os.O_WRONLY), 1)
 
    from ipc.shared_buffer import (
        init_ring_buffer, get_mmap_instance, buffer_lock,
        HEADER_FORMAT, HEADER_SIZE, ORDER_FORMAT, ORDER_SIZE, MAX_ORDERS,
    )
    from matching_engine_core.order_book import PyOrderBook
 
    init_ring_buffer()
    file_handle, mem = get_mmap_instance()
    book = PyOrderBook()
    clock = time.perf_counter_ns
    batch, processed, backlog = [], 0, 0
    book_info = (None, None, 0, 0)
    last_send = last_book = time.time()
 
    try:
        while not stop.is_set():
            got = False
            with buffer_lock(file_handle):
                write_ptr, read_ptr = HEADER_FORMAT.unpack_from(mem, 0)
                if read_ptr < write_ptr:
                    offset = HEADER_SIZE + (read_ptr % MAX_ORDERS) * ORDER_SIZE
                    oid, price, qty, side = ORDER_FORMAT.unpack_from(mem, offset)
                    if side in (BUY, SELL) and price > 0 and qty > 0:
                        t0 = clock()
                        book.process_incoming(oid, price, qty, side)
                        ns = clock() - t0  # time for ONE order inside the engine
                        batch.append((oid, side, price, qty, ns))
                        processed += 1
                    HEADER_FORMAT.pack_into(mem, 0, write_ptr, read_ptr + 1)
                    got = True
                backlog = write_ptr - read_ptr - (1 if got else 0)
 
            now = time.time()
            if now - last_book > 0.5:  # not every order: reading the book is slow
                book_info, last_book = summarize_book(book), now
            if now - last_send > 0.1:
                out_q.put({"orders": batch, "processed": processed,
                           "backlog": backlog, "book": book_info})
                batch, last_send = [], now
            if not got:
                time.sleep(0.0001)
    finally:
        mem.close()
        file_handle.close()
 
 
def fake_worker(out_q, stop):
    """DEMO: pretend orders, so you can test the screen without the engine."""
    n = 0
    while not stop.is_set():
        batch = []
        for _ in range(20):
            n += 1
            batch.append((n, random.choice((BUY, SELL)),
                          random.randint(9950, 10050),
                          random.choice((10, 50, 95, 100)),
                          random.randint(8_000, 45_000)))
        mid = batch[-1][2]
        bid = mid - random.randint(1, 10)
        out_q.put({"orders": batch, "processed": n, "backlog": 0,
                   "book": (bid, bid + random.randint(2, 20), 5, 5)})
        time.sleep(0.1)
 
 
# ---------- 4. Dashboard (curses) ----------
def put(stdscr, row, col, text, attr=0):
    """Write text safely: skip it if the terminal window is too small."""
    h, w = stdscr.getmaxyx()
    if row >= h or col >= w:
        return
    try:
        stdscr.addstr(row, col, text[: w - col - 1], attr)
    except curses.error:
        pass
 
 
def latency_graph(values, width=40):
    """Recent latencies as text: a taller symbol means slower."""
    ramp = " .:-=+*#%@"
    vals = list(values)[-width:]
    if not vals:
        return ""
    hi = max(vals) or 1
    return "".join(ramp[int(v / hi * 9)] for v in vals)
 
 
def price_text(p):
    return f"{p / PRICE_SCALE:8.2f}" if p is not None else "      --"
 
 
def dashboard(stdscr, in_q, ledger_q, demo):
    curses.curs_set(0)
    stdscr.nodelay(True)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
    red, green = curses.color_pair(1), curses.color_pair(2)
 
    stats = LatencyStats()
    recent = deque(maxlen=10)
    samples = deque(maxlen=20)  # (time, total) -> orders per second
    total, backlog = 0, 0
    book = (None, None, 0, 0)
    whale_until = 0.0
 
    while stdscr.getch() != ord("q"):
        try:  # take everything the worker sent since the last frame
            while True:
                msg = in_q.get_nowait()
                total, backlog, book = msg["processed"], msg["backlog"], msg["book"]
                if msg["orders"]:
                    ledger_q.put(msg["orders"])  # one message per batch
                for order in msg["orders"]:
                    stats.add(order[4])
                    recent.append(order)
                    if order[3] >= WHALE_QTY:
                        whale_until = time.time() + 2
        except queue.Empty:
            pass
 
        now = time.time()
        samples.append((now, total))
        t0, n0 = samples[0]
        rate = (total - n0) / (now - t0) if now > t0 else 0.0
        avg, p99, mx = stats.summary_us()
        best_bid, best_ask, n_bids, n_asks = book
 
        stdscr.erase()
        mode = "DEMO: fake data" if demo else "LIVE"
        put(stdscr, 0, 0, f"=== ChronosMatch Latency Monitor [{mode}] ===", curses.A_BOLD)
        put(stdscr, 2, 0, f"Orders processed : {total}")
        put(stdscr, 3, 0, f"Orders/sec       : {rate:,.0f}")
        put(stdscr, 4, 0, f"Waiting in buffer: {backlog}")
        put(stdscr, 5, 0, f"Avg time/order   : {avg:6.1f} us")
        put(stdscr, 6, 0, f"p99 time/order   : {p99:6.1f} us")
        put(stdscr, 7, 0, f"Max time/order   : {mx:6.1f} us")
        ok = avg < 50  # project target: under 50 microseconds
        put(stdscr, 8, 0, "Target <50us     : " + ("OK" if ok else "SLOW"),
            green if ok else red)
        put(stdscr, 9, 0, "Speed graph : [" + latency_graph(stats.values) + "]")
 
        put(stdscr, 2, 40, "ORDER BOOK", curses.A_BOLD)
        put(stdscr, 3, 40, "Best ASK (Sell): " + price_text(best_ask), red)
        put(stdscr, 4, 40, "Best BID (Buy) : " + price_text(best_bid), green)
        spread = None
        if best_bid is not None and best_ask is not None:
            spread = best_ask - best_bid
        put(stdscr, 5, 40, "Spread         : " + price_text(spread))
        put(stdscr, 6, 40, f"Waiting: {n_bids} buys / {n_asks} sells")
        if time.time() < whale_until:
            put(stdscr, 7, 40, "*** WHALE ORDER! ***", red | curses.A_BOLD)
 
        put(stdscr, 11, 0, "Recent orders (red = WHALE):")
        for i, (oid, side, price, qty, ns) in enumerate(reversed(recent)):
            line = (f"#{oid:<8} {'BUY ' if side == BUY else 'SELL'} "
                    f"{price / PRICE_SCALE:8.2f} x {qty:<5} {ns / 1000:6.1f}us")
            put(stdscr, 12 + i, 0, line,
                red | curses.A_BOLD if qty >= WHALE_QTY else 0)
 
        put(stdscr, 23, 0, "Press 'q' to quit")
        stdscr.refresh()
        time.sleep(0.1)
 
 
# ---------- 5. Start everything ----------
def main():
    demo = "--demo" in sys.argv
    if not demo:
        try:
            import matching_engine_core.order_book  # noqa: F401
        except ImportError as err:
            print(f"Cannot load the engine: {err}")
            print("Build it first, from the project folder:")
            print("    python setup.py build_ext --inplace")
            print("Or test the screen without it:")
            print("    python dashboard/latency_dashboard.py --demo")
            return
 
    in_q, ledger_q, stop = Queue(), Queue(), Event()
    worker = Process(target=fake_worker if demo else engine_worker,
                     args=(in_q, stop))
    writer = Process(target=ledger_writer, args=(ledger_q,))
    worker.start()
    writer.start()
    try:
        curses.wrapper(dashboard, in_q, ledger_q, demo)
    finally:
        stop.set()
        worker.join(timeout=2)
        if worker.is_alive():
            worker.terminate()
        ledger_q.put(None)
        writer.join()
    print("Done. Orders saved in ledger.db")
 
 
if __name__ == "__main__":  # this guard is required on Windows
    main()
 