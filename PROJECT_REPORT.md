# ChronosMatch Project Report

## Project objective

ChronosMatch is an internship project prototype for low-latency order
ingestion and matching. It is intended to demonstrate binary IPC with
`mmap`, a Cython price-time-priority order book, asynchronous order
generation, latency visualization, and SQLite execution auditing.

This repository is a local simulator. It does not connect to Nasdaq, NYSE,
or another exchange and is not suitable for real-money trading.

## Implemented components

| Component | Location | Purpose |
|---|---|---|
| Cython matching engine | `matching_engine_core/order_book.pyx` | C-struct order book, price-time matching, execution output, and latency counters. The matching loop releases the GIL. |
| Python reference engine | `matching_engine_core/order_book_fallback.py` | Matching implementation for tests and use when the compiled extension cannot load. It returns fills and shares the book-summary API. |
| Engine loader | `matching_engine_core/engine_loader.py` | Prefers the Cython extension; emits a warning before selecting the fallback. |
| Primary mmap bus | `ipc/shared_buffer.py`, `ipc/order_gateway.py` | Fixed-size `shared.bin` record queue, input validation, pending-order duplicate check, and process locking. |
| Engine consumer | `ipc/engine_core.py` | Reads and processes orders from the primary mmap bus. |
| Async market simulator | `src/market_simulator.py`, `src/main.py` | Generates orders asynchronously and submits them through the same gateway the engine consumes. |
| Terminal dashboard | `dashboard/latency_dashboard.py` | Displays processing latency, order-book top-of-book, backlog, and large-order highlighting; queues fills to a separate SQLite writer process. |
| Django web frontend | `webapp/`, `webdashboard/` | Browser dashboard with live mmap queue status, manual order submission, and recent SQLite fills. |
| Trade ledger | Dashboard SQLite writer; helper in `ipc/trade_ledger.py` | Persists execution records in SQLite for audit. |
| Secondary ring-buffer example | `src/mmap_ring_buffer.py` | Standalone, typed order record ring buffer with status statistics; retained for focused tests and learning. It is not the primary live IPC bus. |

## Work completed in this pass

1. **Connected the entry point to the actual IPC pipeline.** `src.main` now
   delegates to the async simulator, which submits through
   `ipc.order_gateway`; it no longer writes to an unrelated
   `chronosmatch_ring_buffer.dat` file.
2. **Made the simulator usable for burst tests.** The default inter-order
   delay is zero, every generated item yields control to the event loop, and
   per-order printing is opt-in with `--verbose`. Invalid sides and
   non-finite delays produce explicit errors.
3. **Fixed the fallback engine contract.** The Python book now returns maker,
   taker, execution price, quantity, and side for each fill, and implements
   the same summary and imbalance APIs used by the compiled engine.
4. **Added execution output to the Cython engine.** Matching still happens
   on C data in the GIL-free section; it writes fills to a C allocation and
   creates Python dictionaries only after matching completes. Calls against
   one book are serialized with a lock, while separate books can match
   independently.
5. **Connected fills to the audit ledger.** The live dashboard consumer
   batches execution rows and sends them to its separate SQLite writer
   process.
6. **Made engine loading explicit and resilient.** If the compiled extension
   fails to import, the consumer can use the Python reference implementation
   and emits a warning instead of failing before the demo starts.
7. **Fixed dashboard buffer monitoring.** The standalone mmap ring buffer
   now provides the `get_stats()` method used by its monitor.
8. **Isolated gateway tests.** Tests now supply a mocked IPC module instead
   of reading or mutating the real `shared.bin` file.
9. **Removed per-order mmap flushing.** Shared mappings make producer writes
   visible to other mapped processes; flushing each record is for disk
   durability and imposed avoidable overhead on the submission path.
10. **Reduced queue lock contention.** Producers write a validated batch and
    publish its write pointer once. Consumers copy and release each record
    under the file lock, then run matching after releasing it.
11. **Fixed standalone engine shutdown reporting.** The engine returns its
    order book to the module entry point so market-imbalance reporting does
    not reference a local variable outside its scope.
12. **Added a Django presentation layer.** The browser UI polls live shared
    queue and ledger status and submits validated order tickets through the
    existing IPC gateway. It is a local demo UI, not an exchange connection.
13. **Connected the standalone engine to the web ledger.** Engine fills are
    queued to a background SQLite writer using the same project-root
    `ledger.db` and `executed_trades` schema read by the Django status API.
14. **Made whale highlighting match the project criterion.** The live
    terminal dashboard now highlights a large incoming order only if its
    fills span multiple price levels. The terminal's fake demo can still
    display explicitly simulated whale highlights.

## Week 3 write-up: C-level optimization and metrics

The matching book is represented by Cython C structs and linked price
levels/orders. The crossing, queue-priority, and quantity-update loop runs
inside `nogil`; Python dictionaries for execution records are constructed
after the native matching call. The native trade-record buffer grows only
when a fill occurs, rather than allocating space for every resting order on
each incoming order. A per-book lock protects state while the GIL is
released.

The engine captures `perf_counter_ns()` timestamps immediately before and
after the native matching call and exposes last, average, maximum, and sample
count metrics. The terminal monitor separately shows per-order time, recent
latency distribution, order rate, backlog, and best bid/ask. Those are local
process measurements, not exchange round-trip latency. The code avoids
Python object operations in the matching loop; it does not claim that Python
garbage collection is disabled for the whole application.

Validation completed: the Cython extension compiled successfully on the
project environment; matching tests cover partial fills and price/FIFO
priority, and a compiled-extension smoke test verified fill output and the
remaining order quantity. No sustained benchmark result or under-50-us
guarantee has been established.

## Week 4 write-up: audit resiliency and final presentation

The engine forwards execution batches to a background SQLite writer. The
terminal-dashboard run uses a separate writer process, and the standalone
engine uses a writer thread, so ledger writes are kept out of the matching
function. Both use the project-root `ledger.db` and `executed_trades` schema;
the Django dashboard polls that ledger and the mmap queue and can submit
orders through the existing gateway. The web order page and queue status
were checked through Django's test client and local HTTP requests.

The terminal UI shows large-order highlighting only when an order of the
configured large-order size fills at more than one price level. The project
report, README, test commands, and local Django run instructions are
available for the final demonstration.

Validation completed: Django system checks passed; all 43 project tests
passed, including all 4 Django-specific tests; and the Cython extension
rebuilt successfully. The one-million-order benchmark and sustained
throughput/latency targets have not been run/verified in this final pass.
This remains an educational local simulator, not a production or
exchange-connected trading system.

## How to run and validate

From the project root:

```powershell
python -m pip install -r requirements.txt
python setup.py build_ext --inplace
python -m unittest discover -v
```

Start the browser dashboard with `python manage.py runserver`, open
`http://127.0.0.1:8000/`, and run `python -m ipc.engine_core` in another
terminal to consume submitted orders.

For the interactive run, start `python dashboard/latency_dashboard.py`,
then in a second terminal run:

```powershell
python -m src.main --orders 10000 --delay 0
```

For the no-input screen demo use
`python dashboard/latency_dashboard.py --demo`. The standalone consumer can
instead be run with `python -m ipc.engine_core`; run only one consumer against
the shared queue at a time.

The explicit million-record test is
`python -m tests.test_ipc_million`. It resets `shared.bin`; stop all queue
users and retain any pending data before running it.

## Known limitations and interpretation

- The extension must be rebuilt after changing the `.pyx` file. A pre-existing
  `.pyd` is not proof that the current source compiled or loaded successfully.
- A local Windows application-control policy may block `.pyd` loading. The
  fallback preserves function but cannot substantiate the Cython performance
  target.
- The gateway's pending-ID duplicate check scans queued records once per
  submitted batch. This favors correctness over high producer throughput
  under a large backlog. The one-million-order IPC benchmark writes directly
  to the mmap queue and does not measure that gateway path.
- The dashboard's engine-call time is not network-to-engine end-to-end
  latency. The primary shared record does not carry an ingress timestamp.
- The standalone engine uses a background writer thread, while the terminal
  dashboard uses a separate writer process. Neither mode is a durable,
  replicated production ledger.
- The 50-microsecond execution objective and 100,000-orders/second generation
  target are goals, not measured guarantees. Report actual results only after
  benchmarking the compiled engine and full producer/consumer path on the
  target machine.
- `shared.bin` is persistent and may contain unread orders between runs.
  Reset it only after stopping all users and deciding that pending records
  can be discarded.
