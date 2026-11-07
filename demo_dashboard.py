
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox

ROOT = Path(__file__).resolve().parent
IPC_DIR = ROOT / "ipc"
sys.path.insert(0, str(IPC_DIR))

import order_gateway as gateway


class ChronosMatchDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("ChronosMatch | Order Gateway Dashboard")
        self.root.geometry("900x700")
        self.root.minsize(760, 600)

        self.root.protocol("WM_DELETE_WINDOW", self.close_app)

        self.build_ui()
        self.refresh_buffer()

    def build_ui(self):
        header = ttk.Frame(self.root, padding=16)
        header.pack(fill="x")

        ttk.Label(
            header,
            text="CHRONOSMATCH",
            font=("Segoe UI", 22, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            header,
            text="Order Gateway and Shared-Memory Monitor",
        ).pack(anchor="w")

        # Live buffer information
        stats = ttk.LabelFrame(
            self.root, text="Shared-Memory Ring Buffer", padding=12
        )
        stats.pack(fill="x", padx=16, pady=6)

        self.write_var = tk.StringVar(value="Write pointer: —")
        self.read_var = tk.StringVar(value="Read pointer: —")
        self.occupancy_var = tk.StringVar(value="Queued orders: —")

        ttk.Label(stats, textvariable=self.write_var).grid(
            row=0, column=0, sticky="w", padx=8, pady=5
        )
        ttk.Label(stats, textvariable=self.read_var).grid(
            row=0, column=1, sticky="w", padx=8, pady=5
        )
        ttk.Label(stats, textvariable=self.occupancy_var).grid(
            row=1, column=0, columnspan=2, sticky="w",
            padx=8, pady=5
        )

        # Order entry form
        form = ttk.LabelFrame(
            self.root, text="Submit an Order", padding=12
        )
        form.pack(fill="x", padx=16, pady=6)

        self.order_id = tk.StringVar(value="101")
        self.price = tk.StringVar(value="15000")
        self.quantity = tk.StringVar(value="5")
        self.side = tk.StringVar(value="BUY")

        fields = [
            ("Order ID", self.order_id),
            ("Price", self.price),
            ("Quantity", self.quantity),
        ]

        for row, (label, variable) in enumerate(fields):
            ttk.Label(form, text=label).grid(
                row=row, column=0, sticky="w", padx=6, pady=6
            )
            ttk.Entry(
                form, textvariable=variable, width=24
            ).grid(row=row, column=1, sticky="w", padx=6, pady=6)

        ttk.Label(form, text="Side").grid(
            row=3, column=0, sticky="w", padx=6, pady=6
        )
        ttk.Combobox(
            form,
            textvariable=self.side,
            values=("BUY", "SELL"),
            state="readonly",
            width=21,
        ).grid(row=3, column=1, sticky="w", padx=6, pady=6)

        actions = ttk.Frame(form)
        actions.grid(
            row=4, column=0, columnspan=2,
            sticky="w", padx=6, pady=10
        )

        ttk.Button(
            actions, text="Submit Order", command=self.submit_order
        ).pack(side="left", padx=(0, 8))

        ttk.Button(
            actions, text="Run Unit Tests", command=self.run_tests
        ).pack(side="left")

        # Activity log
        activity = ttk.LabelFrame(
            self.root, text="Gateway Activity", padding=12
        )
        activity.pack(
            fill="both", expand=True, padx=16, pady=6
        )

        self.log = tk.Text(
            activity, height=12, wrap="word",
            font=("Consolas", 10), state="disabled"
        )
        self.log.pack(fill="both", expand=True)

        self.add_log("Dashboard started.")
        self.add_log("Connected to the Python order gateway.")
        self.add_log(
            "Submit a valid or invalid order to demonstrate validation."
        )

        self.test_status = tk.StringVar(
            value="Unit tests have not been run from this dashboard."
        )
        ttk.Label(
            self.root, textvariable=self.test_status, padding=10
        ).pack(fill="x")

    def add_log(self, message):
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def refresh_buffer(self):
        try:
            memory = gateway.shared_memory
            header_size = gateway.HEADER_SIZE

            write_ptr, read_ptr = gateway.HEADER_FORMAT.unpack(
                memory[:header_size]
            )

            queued = write_ptr - read_ptr

            self.write_var.set(f"Write pointer: {write_ptr}")
            self.read_var.set(f"Read pointer: {read_ptr}")
            self.occupancy_var.set(
                f"Queued orders: {queued} / {gateway.MAX_ORDERS}"
            )

        except Exception as exc:
            self.add_log(f"Buffer monitor error: {exc}")

        self.root.after(1000, self.refresh_buffer)

    def submit_order(self):
        try:
            oid = int(self.order_id.get().strip())
            price = int(self.price.get().strip())
            quantity = int(self.quantity.get().strip())
            side = 1 if self.side.get() == "BUY" else 2

        except ValueError:
            messagebox.showerror(
                "Invalid input",
                "Order ID, price, and quantity must be integers.",
            )
            return

        try:
            accepted = gateway.produce_order(
                order_id=oid,
                price=price,
                quantity=quantity,
                side=side,
            )

            if accepted:
                self.add_log(
                    f"ACCEPTED | ID={oid} | Price={price} | "
                    f"Quantity={quantity} | Side={self.side.get()}"
                )
            else:
                self.add_log(
                    f"REJECTED | ID={oid} | "
                    "Gateway validation or capacity check failed."
                )

            self.refresh_buffer_now()

        except Exception as exc:
            self.add_log(f"Gateway error: {exc}")
            messagebox.showerror("Gateway error", str(exc))

    def refresh_buffer_now(self):
        try:
            write_ptr, read_ptr = gateway.HEADER_FORMAT.unpack(
                gateway.shared_memory[:gateway.HEADER_SIZE]
            )
            self.write_var.set(f"Write pointer: {write_ptr}")
            self.read_var.set(f"Read pointer: {read_ptr}")
            self.occupancy_var.set(
                f"Queued orders: {write_ptr - read_ptr} / "
                f"{gateway.MAX_ORDERS}"
            )
        except Exception as exc:
            self.add_log(f"Buffer refresh error: {exc}")

    def run_tests(self):
        self.test_status.set("Running unit tests...")
        self.root.update_idletasks()

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    "tests",
                    "-v",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=60,
            )

            output = result.stdout + "\n" + result.stderr
            self.add_log("----- UNIT TEST RESULTS -----")
            self.add_log(output.strip()[-5000:])

            if result.returncode == 0:
                self.test_status.set("Unit tests passed.")
                self.add_log("TEST RESULT: PASS")
            else:
                self.test_status.set("Unit tests failed. Check activity log.")
                self.add_log("TEST RESULT: FAIL")

        except Exception as exc:
            self.test_status.set("Unable to run unit tests.")
            self.add_log(f"Test runner error: {exc}")

    def close_app(self):
        try:
            gateway.shared_memory.flush()
            gateway.shared_memory.close()
            gateway.file_handle.close()
        except Exception:
            pass

        self.root.destroy()


if __name__ == "__main__":
    window = tk.Tk()
    app = ChronosMatchDashboard(window)
    window.mainloop()
