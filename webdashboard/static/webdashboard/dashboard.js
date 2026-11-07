(() => {
  const number = new Intl.NumberFormat();
  const money = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
  });
  const $ = (id) => document.getElementById(id);

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
        trade.executed_at || "—",
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

  async function refresh() {
    try {
      const response = await fetch("/api/status/", {
        headers: { "Accept": "application/json" },
        cache: "no-store",
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Status unavailable");

      const queue = data.queue;
      $("engine-status").textContent = "QUEUE ONLINE";
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
      renderTrades(data.trades || []);
    } catch (error) {
      $("engine-status").textContent = "DISCONNECTED";
      $("queue-status-tag").textContent = "OFFLINE";
      $("queue-status-tag").style.color = "var(--red)";
      $("ledger-status").textContent = "UNAVAILABLE";
      $("ledger-status").style.color = "var(--red)";
      $("trades-body").innerHTML = `<tr><td class="empty-state" colspan="6">${error.message}</td></tr>`;
    }
  }

  updateClock();
  refresh();
  window.setInterval(updateClock, 1000);
  window.setInterval(refresh, 2000);
})();
