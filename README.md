# ChronosMatch

ChronosMatch is an educational low-latency trading-engine prototype. It
demonstrates a memory-mapped order queue, a Cython limit-order book, an
asyncio market simulator, a terminal dashboard, and asynchronous SQLite
trade auditing. It is not connected to a real exchange and is not production
trading software.

## Architecture

The simulator submits integer orders to `ipc.order_gateway`. The gateway and
consumer share `shared.bin`, a file-backed memory map in the project root.
Its 16-byte header contains monotonically increasing write/read positions;
each 16-byte record stores an unsigned 32-bit order ID, price in cents,
quantity, and side (`1` = BUY, `2` = SELL). The configured queue holds
1,000,000 records. Processes coordinate updates with a cross-process file
lock; producers publish batches atomically, and consumers copy/dequeue a
record under the lock before matching it outside the critical section.

The consumer uses the Cython engine when the extension is built and loadable.
Matching uses typed C structs and pointers in a `nogil` section, enforces
price-time priority, and returns execution records after matching. If the
extension cannot load, ChronosMatch reports a warning and uses the Python
reference engine so that the demo remains usable.

The curses dashboard can run its own consumer and separate SQLite writer.
Executed fills are stored in `ledger.db` in the `executed_trades` table.
The standalone `src.mmap_ring_buffer.RingBuffer` is retained as a smaller
ring-buffer example and is not the live `shared.bin` bus.
The Django API reads the engine heartbeat and latency aggregates from the
same SQLite/WAL database as the audited executions.

## Setup

Use Python 3.10 or newer. From the project root:

```powershell
python -m pip install -r requirements.txt
python setup.py build_ext --inplace
```

Building the Cython extension requires a working C compiler. On Windows,
install the Microsoft C++ Build Tools. If a security policy prevents loading
the compiled extension, the application will warn and use the Python
fallback; that mode is functional but is not a low-latency performance mode.

## Run

### Django web dashboard

Install the requirements and build the Cython extension once:

```powershell
python -m pip install -r requirements.txt
python setup.py build_ext --inplace
```

Start the engine and Django web server together:

```powershell
python manage.py runchronos
```

Open `http://127.0.0.1:8000/`. The page refreshes queue depth, engine status,
average/last/maximum match latency, and recent audited fills automatically.
Submit manual BUY/SELL limit orders from the order ticket. Stop the combined
demo with `Ctrl+C`; the engine writes its final metrics and drains its audit
queue before exiting. To run the web server separately, use
`python manage.py runserver` and run `python -m ipc.engine_core` in another
terminal.

The web server and engine both use the project-root `shared.bin`.
The development server is intended for local demos only; `DEBUG=True`, the
development key, and host configuration must be changed before deployment.
The dashboard reports engine-call latency measured locally around each
matching call; this is not network or exchange round-trip latency.

For a complete dashboard demonstration, start the dashboard first:

```powershell
python dashboard/latency_dashboard.py
```

In another terminal, generate and submit orders:

```powershell
python -m src.main --orders 10000 --delay 0
```

`--delay 0` generates cooperative batches of up to 256 orders. Add `--verbose`
to print every order; per-order console output reduces throughput. To run the
engine without the dashboard, use `python -m ipc.engine_core` in one terminal
and the simulator command in another. Do not start both consumers against
the same queue at once.

To check the dashboard without starting the engine or simulator:

```powershell
python dashboard/latency_dashboard.py --demo
```

The dashboard uses curses. On Windows the `windows-curses` dependency is
installed by `requirements.txt`.

## Tests and IPC benchmark

Run the unit tests from the project root:

```powershell
python -m unittest discover -v
```

The million-order IPC benchmark is an explicit, longer-running command:

```powershell
python -m tests.test_ipc_million
```

It resets `shared.bin` before running. Stop all producers and consumers first,
and preserve any pending orders you need before using the benchmark. The
benchmark isolates mmap transport and uses the Python reference book; it is
not an end-to-end simulator throughput or Cython latency result.

## Measurement notes

The dashboard reports per-order processing time measured around the engine
call. The Cython engine also tracks its matching-call latency in nanoseconds.
Neither value is a measured exchange/network round trip, and no specific
50-microsecond or 100,000-orders/second result is guaranteed. Results depend
on the build, machine, operating system, and queue load. Benchmark the built
extension separately from the fallback before making performance claims.

See [PROJECT_REPORT.md](PROJECT_REPORT.md) for the module inventory, completed
work, verification steps, and known limitations.
