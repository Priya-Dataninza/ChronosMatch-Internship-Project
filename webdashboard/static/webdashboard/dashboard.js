(() => {
  const number = new Intl.NumberFormat();
  const money = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
  });
  const executionTimeFormat = new Intl.DateTimeFormat("en-GB", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
  const $ = (id) => document.getElementById(id);
  const statusUrl = document.body.dataset.statusUrl || "/api/status/";
  const latencyUs = (nanoseconds) => (
    Number.isFinite(nanoseconds) ? (nanoseconds / 1000).toFixed(2) : "—"
  );
  const formatExecutionTime = (timestamp) => {
    if (!timestamp) return "—";
    const hasTimezone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(timestamp);
    const isoTimestamp = hasTimezone
      ? timestamp
      : `${timestamp.replace(" ", "T")}Z`;
    const date = new Date(isoTimestamp);
    return Number.isNaN(date.getTime())
      ? timestamp
      : executionTimeFormat.format(date);
  };
  let previousProcessed = null;
  let previousSampleTime = null;
  let currentEngineStatus = "unknown";
  let currentEngineManaged = false;
  const latencyHistory = [];
  const maxLatencySamples = 60;

  function updateClock() {
    $("local-clock").textContent = new Intl.DateTimeFormat("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(new Date());
  }

  function renderTrades(trades) {
    const body = $("trades-body");
    if (!trades.length) {
      body.innerHTML = '<tr><td class="empty-state" colspan="6">No fills yet — start the engine and submit crossing orders to see executions.</td></tr>';
      return;
    }

    body.replaceChildren(...trades.map((trade) => {
      const sideClass = trade.side === "BUY" ? "side-buy" : "side-sell";
      const row = document.createElement("tr");
      const values = [
        `#${trade.maker_order_id}`,
        `#${trade.taker_order_id}`,
        trade.side,
        money.format(trade.price),
        number.format(trade.quantity),
        formatExecutionTime(trade.executed_at),
      ];
      values.forEach((value, index) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        if (index === 2) cell.classList.add(sideClass);
        row.append(cell);
      });
      return row;
    }));
  }

  function renderBookSide(bodyId, levels, emptyText, sideClass) {
    const body = $(bodyId);
    if (!levels.length) {
      body.innerHTML = `<tr><td class="empty-state" colspan="3">${emptyText}</td></tr>`;
      return;
    }

    body.replaceChildren(...levels.map((level) => {
      const row = document.createElement("tr");
      const values = [
        money.format(level.price / 100),
        number.format(level.quantity),
        number.format(level.order_count),
      ];
      values.forEach((value, index) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        if (index === 0) cell.classList.add(sideClass);
        row.append(cell);
      });
      return row;
    }));
  }

  function renderOrderBook(book) {
    renderBookSide("bids-body", book.bids, "No resting bids", "side-buy");
    renderBookSide("asks-body", book.asks, "No resting asks", "side-sell");

    const summary = book.summary || {
      bid_order_count: book.bids.reduce(
        (total, level) => total + level.order_count, 0
      ),
      ask_order_count: book.asks.reduce(
        (total, level) => total + level.order_count, 0
      ),
      total_bid_quantity: book.bids.reduce(
        (total, level) => total + level.quantity, 0
      ),
      total_ask_quantity: book.asks.reduce(
        (total, level) => total + level.quantity, 0
      ),
    };
    if ($("bid-order-count")) {
      $("bid-order-count").textContent = number.format(
        summary.bid_order_count
      );
      $("ask-order-count").textContent = number.format(
        summary.ask_order_count
      );
      $("bid-total-quantity").textContent = number.format(
        summary.total_bid_quantity
      );
      $("ask-total-quantity").textContent = number.format(
        summary.total_ask_quantity
      );
      $("book-summary-note").textContent = book.summary
        ? "Across all resting price levels"
        : "Totals for the visible top 10 price levels";
    }
  }

  function renderLatencyChart(engine) {
    const chart = $("latency-chart");
    if (!chart) return;

    if (
      engine.status === "running"
      && Number.isFinite(engine.last_latency_ns)
    ) {
      latencyHistory.push({
        last: engine.last_latency_ns,
        average: Number.isFinite(engine.average_latency_ns)
          ? engine.average_latency_ns
          : engine.last_latency_ns,
      });
      if (latencyHistory.length > maxLatencySamples) latencyHistory.shift();
    }

    const note = $("latency-chart-note");
    if (!latencyHistory.length) {
      note.textContent = "Waiting for engine samples.";
      return;
    }

    const maxNs = Math.max(
      1000,
      ...latencyHistory.flatMap((sample) => [sample.last, sample.average])
    );
    const xFor = (index) => (
      latencyHistory.length === 1
        ? 52
        : 52 + index * (573 / (latencyHistory.length - 1))
    );
    const yFor = (value) => 185 - (value / maxNs) * 150;
    const points = (key) => latencyHistory.map(
      (sample, index) => `${xFor(index).toFixed(1)},${yFor(sample[key]).toFixed(1)}`
    ).join(" ");

    $("latency-current-line").setAttribute("points", points("last"));
    $("latency-average-line").setAttribute("points", points("average"));
    $("latency-axis-max").textContent = `${latencyUs(maxNs)} µs`;
    $("latency-axis-mid").textContent = `${latencyUs(maxNs / 2)} µs`;
    note.textContent = engine.status === "running"
      ? `${latencyHistory.length} samples · latest ${latencyUs(engine.last_latency_ns)} µs`
      : `Engine ${engine.status}; showing the last ${latencyHistory.length} samples.`;
  }

  function updateEngineControls(status, managed = false) {
    const controls = $("engine-controls");
    if (!controls) return;
    const running = status === "running";
    $("engine-on").disabled = status !== "stopped" && status !== "stale";
    $("engine-off").disabled = !managed || (!running && status !== "stale");
    $("engine-off").title = managed
      ? "Stop the engine started by this dashboard"
      : "This engine must be stopped from the terminal that started it";
    $("simulate-bulk").disabled = !running;
  }

  function showControlMessage(message, isError = false) {
    const element = $("control-message");
    if (!element) return;
    element.textContent = message;
    element.classList.toggle("error", isError);
  }

  async function postControl(url, button) {
    const controls = $("engine-controls");
    if (!controls) return;

    const csrfToken = document.querySelector(
      "#order-entry [name=csrfmiddlewaretoken]"
    )?.value;
    button.disabled = true;
    showControlMessage("Sending request…");
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Accept": "application/json",
          "X-CSRFToken": csrfToken,
        },
      });
      let data;
      try {
        data = await response.json();
      } catch {
        throw new Error(`Request failed (${response.status})`);
      }
      if (!response.ok) {
        throw new Error(data.error || `Request failed (${response.status})`);
      }
      showControlMessage(data.message);
      await refresh();
    } catch (error) {
      showControlMessage(
        error instanceof Error ? error.message : "Unexpected control error",
        true
      );
    } finally {
      updateEngineControls(currentEngineStatus, currentEngineManaged);
    }
  }

  function renderUnavailable(error) {
    previousProcessed = null;
    previousSampleTime = null;
    currentEngineStatus = "unavailable";
    currentEngineManaged = false;
    $("engine-status").textContent = "STATUS UNAVAILABLE";
    $("engine-status").style.color = "var(--red)";
    $("engine-guidance").hidden = false;
    $("engine-guidance").textContent =
      `Dashboard status unavailable: ${error.message}`;
    $("queue-status-tag").textContent = "OFFLINE";
    $("queue-status-tag").style.color = "var(--red)";
    $("queued-orders").textContent = "—";
    $("free-capacity").textContent = "—";
    $("usage-percent").textContent = "—";
    $("pending-secondary").textContent = "—";
    $("free-secondary").textContent = "—";
    $("queue-meter").style.width = "0";
    $("buffer-fill").style.width = "0";
    $("engine-latency").textContent = "—";
    $("engine-counts").textContent = "—";
    $("engine-latency-foot").textContent = "Engine status unavailable";
    const ordersPerSecond = $("orders-per-second");
    if (ordersPerSecond) ordersPerSecond.textContent = "—";
    if ($("latency-chart-note")) {
      $("latency-chart-note").textContent = "Engine status unavailable.";
    }
    updateEngineControls("unavailable");
    $("ledger-status").textContent = "UNAVAILABLE";
    $("ledger-status").style.color = "var(--red)";
    renderOrderBook({ bids: [], asks: [] });

    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.className = "empty-state";
    cell.colSpan = 6;
    cell.textContent = error.message;
    row.append(cell);
    $("trades-body").replaceChildren(row);
  }

  async function refresh() {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch(statusUrl, {
        headers: { "Accept": "application/json" },
        cache: "no-store",
        signal: controller.signal,
      });
      let data;
      try {
        data = await response.json();
      } catch {
        throw new Error(`Status request failed (${response.status})`);
      }
      if (!response.ok) {
        throw new Error(data.error || `Status request failed (${response.status})`);
      }

      const queue = data.queue;
      const engine = data.engine || { status: "unavailable" };
      const sampleTime = performance.now();
      const processed = engine.orders_processed || 0;
      const ordersPerSecond = (
        previousProcessed !== null
        && previousSampleTime !== null
        && processed >= previousProcessed
      )
        ? (processed - previousProcessed)
          / ((sampleTime - previousSampleTime) / 1000)
        : 0;
      previousProcessed = processed;
      previousSampleTime = sampleTime;
      const engineRunning = engine.status === "running";
      currentEngineStatus = engine.status;
      currentEngineManaged = data.engine_managed === true;
      $("engine-status").textContent = engineRunning
        ? `ENGINE RUNNING · ${(engine.engine_type || "UNKNOWN").toUpperCase()}`
        : `ENGINE ${engine.status.toUpperCase()}`;
      $("engine-status").style.color = engineRunning
        ? "var(--green)"
        : "var(--red)";
      updateEngineControls(engine.status, currentEngineManaged);
      $("engine-guidance").hidden = engineRunning;
      $("engine-latency").textContent = latencyUs(
        engine.average_latency_ns
      );
      $("engine-counts").textContent =
        `${number.format(processed)} orders · ${number.format(engine.trades_executed || 0)} fills`;
      const rateElement = $("orders-per-second");
      if (rateElement) {
        rateElement.textContent = number.format(Math.round(ordersPerSecond));
      }
      renderLatencyChart(engine);
      $("engine-latency-foot").textContent = engineRunning
        ? `last ${latencyUs(engine.last_latency_ns)} µs · max ${latencyUs(engine.max_latency_ns)} µs`
        : `Engine ${engine.status}; start runchronos`;
      $("queue-status-tag").textContent = "ONLINE";
      $("queued-orders").textContent = number.format(queue.queued);
      $("free-capacity").textContent = number.format(queue.free);
      $("total-capacity").textContent = number.format(queue.capacity);
      $("usage-percent").textContent = queue.usage_percent.toFixed(2);
      $("pending-secondary").textContent = number.format(queue.queued);
      $("free-secondary").textContent = number.format(queue.free);
      $("queue-meter").style.width = `${Math.min(queue.usage_percent, 100)}%`;
      $("buffer-fill").style.width = `${Math.min(queue.usage_percent, 100)}%`;
      $("ledger-status").textContent = data.ledger_status.toUpperCase();
      $("ledger-status").style.color = data.ledger_status === "online"
        ? "var(--green)"
        : "var(--muted)";
      renderOrderBook(engine.order_book || { bids: [], asks: [] });
      renderTrades(data.trades || []);
    } catch (error) {
      renderUnavailable(
        error instanceof Error ? error : new Error("Unexpected status error")
      );
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function updateActiveNavigation() {
    const currentHash = [...document.querySelectorAll(".nav-link")]
      .some((link) => link.hash === window.location.hash)
      ? window.location.hash
      : "#overview";
    document.querySelectorAll(".nav-link").forEach((link) => {
      link.classList.toggle("active", link.hash === currentHash);
    });
  }

  updateClock();
  updateActiveNavigation();
  window.addEventListener("hashchange", updateActiveNavigation);
  const controls = $("engine-controls");
  if (controls) {
    $("engine-on").addEventListener("click", (event) => {
      postControl(controls.dataset.engineOnUrl, event.currentTarget);
    });
    $("engine-off").addEventListener("click", (event) => {
      postControl(controls.dataset.engineOffUrl, event.currentTarget);
    });
    $("simulate-bulk").addEventListener("click", (event) => {
      postControl(controls.dataset.simulateUrl, event.currentTarget);
    });
  }
  updateEngineControls("unknown");
  window.setInterval(updateClock, 1000);
  async function poll() {
    await refresh();
    window.setTimeout(poll, 2000);
  }
  poll();
})();
