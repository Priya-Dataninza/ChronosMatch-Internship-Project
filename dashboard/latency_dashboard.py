"""
ChronosMatch - Latency Dashboard + SQLite Ledger (Member 4)
NOTE: trades and best bid/ask are FAKE for now.
TODO: replace fake_trade() with real trades from the engine.
Runs with FAKE trades now. Later, replace fake_trade() with real
trades read from the shared mmap ring buffer.

Windows: pip install windows-curses
Run:     python dashboard/latency_dashboard.py     (press q to quit)
"""
import curses
import queue
import random
import sqlite3
import struct
import time
from collections import deque
from multiprocessing import Process, Queue

# One matched trade as raw bytes. AGREE ON THIS FORMAT WITH YOUR TEAM.
# Same style as the team's ORDER_FORMAT (whole numbers, little-endian).
# trade_id, buy_order_id, sell_order_id, price, quantity, latency_ns
TRADE_FMT = struct.Struct("<IIIIIQ")
WHALE_QTY = 1000  # quantity at or above this = "whale" trade
PRICE_SCALE = 100  # ASSUMPTION: price 10025 means 100.25. Confirm with team.


# ---------- 1. SQLite ledger (separate process) ----------
def ledger_writer(q, db_path="ledger.db"):
    con = sqlite3.connect(db_path)
    con.execute(
        "CREATE TABLE IF NOT EXISTS trades("
        "trade_id INTEGER, buy_id INTEGER, sell_id INTEGER, "
        "price INTEGER, qty INTEGER, latency_ns INTEGER)"
    )
    batch, last = [], time.time()

    def flush():
        if batch:
            con.executemany("INSERT INTO trades VALUES (?,?,?,?,?,?)", batch)
            con.commit()
            batch.clear()

    while True:
        try:
            item = q.get(timeout=0.2)
        except queue.Empty:
            item = None
        if item == "STOP":
            break
        if item is not None:
            batch.append(TRADE_FMT.unpack(item))
        # save in groups: faster than one insert per trade
        if len(batch) >= 500 or time.time() - last > 0.5:
            flush()
            last = time.time()
    flush()
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


# ---------- Real timing of the team's engine ----------
def timed_process(book, order_id, price, qty, side):
    """Send ONE order to the real engine; return how many ns it took."""
    t0 = time.perf_counter_ns()
    book.process_incoming(order_id, price, qty, side)
    return time.perf_counter_ns() - t0


# ---------- Fake data (replace with ring buffer reads) ----------
trade_counter = 0


def fake_trade():
    global trade_counter
    trade_counter += 1
    qty = random.choice([10, 50, 100, 500, 2000])
    price = random.randint(9950, 10050)  # whole number like the engine
    latency = random.randint(8_000, 45_000)  # 8-45 microseconds in ns
    return TRADE_FMT.pack(trade_counter, trade_counter * 2, trade_counter * 2 + 1,
                          price, qty, latency)


# ---------- 3. Dashboard ----------
def latency_graph(values, width=40):
    """Draw recent latencies as text: a taller symbol means slower."""
    ramp = " .:-=+*#%@"
    vals = list(values)[-width:]
    if not vals:
        return ""
    hi = max(vals) or 1
    return "".join(ramp[int(v / hi * 9)] for v in vals)



def dashboard(stdscr, q):
    curses.curs_set(0)
    stdscr.nodelay(True)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)

    stats, recent = LatencyStats(), deque(maxlen=10)
    total, start = 0, time.time()
    last_price = 10000

    while stdscr.getch() != ord("q"):
        # Get new trades (fake now; later read from the ring buffer)
        for _ in range(20):
            raw = fake_trade()
            q.put(raw)  # send to ledger process
            t = TRADE_FMT.unpack(raw)
            stats.add(t[5])
            recent.append(t)
            last_price = t[3]
            total += 1

        avg, p99, mx = stats.summary_us()
        rate = total / max(time.time() - start, 0.001)

        stdscr.erase()
        stdscr.addstr(0, 0, "=== ChronosMatch Latency Monitor ===", curses.A_BOLD)
        stdscr.addstr(2, 0, f"Trades total : {total}")
        stdscr.addstr(3, 0, f"Trades/sec   : {rate:,.0f}")
        stdscr.addstr(4, 0, f"Avg latency  : {avg:6.1f} us")
        stdscr.addstr(5, 0, f"p99 latency  : {p99:6.1f} us")
        stdscr.addstr(6, 0, f"Max latency  : {mx:6.1f} us")
        ok = avg < 50  # project target: under 50 microseconds
        stdscr.addstr(7, 0, "Target <50us : " + ("OK" if ok else "SLOW"),
                      curses.color_pair(2 if ok else 1))

        # Order book panel. FAKE values for now: replace bid/ask with the
        # real best bid / best ask from the engine when it exposes them.
        bid = last_price - random.randint(1, 10)
        ask = bid + random.randint(2, 20)
        stdscr.addstr(2, 40, "ORDER BOOK (fake data)", curses.A_BOLD)
        stdscr.addstr(3, 40, f"Best ASK (Sell): {ask / PRICE_SCALE:8.2f}", curses.color_pair(1))
        stdscr.addstr(4, 40, f"Best BID (Buy) : {bid / PRICE_SCALE:8.2f}", curses.color_pair(2))
        stdscr.addstr(5, 40, f"Spread         : {(ask - bid) / PRICE_SCALE:8.2f}")
        stdscr.addstr(8, 0, "Speed graph : [" + latency_graph(stats.values) + "]")

        stdscr.addstr(9, 0, "Recent trades (red = WHALE):")
        for i, t in enumerate(reversed(recent)):
            line = f"#{t[0]:<7} {t[3] / PRICE_SCALE:8.2f} x {t[4]:<5} {t[5] / 1000:5.1f}us"
            attr = curses.color_pair(1) | curses.A_BOLD if t[4] >= WHALE_QTY else 0
            stdscr.addstr(10 + i, 0, line, attr)

        stdscr.addstr(21, 0, "Press 'q' to quit")
        stdscr.refresh()
        time.sleep(0.1)


if __name__ == "__main__":  # this guard is required on Windows
    q = Queue()
    writer = Process(target=ledger_writer, args=(q,))
    writer.start()
    try:
        curses.wrapper(dashboard, q)
    finally:
        q.put("STOP")
        writer.join()
    print("Done. Trades saved in ledger.db")
