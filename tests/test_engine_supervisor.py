import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ipc import engine_supervisor


class FakeProcess:
    pid = 4321

    def __init__(self):
        self.running = True
        self.wait_timeout = None

    def poll(self):
        return None if self.running else 0

    def wait(self, timeout):
        self.wait_timeout = timeout
        self.running = False
        return 0


class TestEngineSupervisor(unittest.TestCase):
    def setUp(self):
        self.original_process = engine_supervisor._engine_process
        self.original_engine_pid = engine_supervisor._engine_pid
        self.original_stop_file = engine_supervisor._stop_file
        self.original_ready_file = engine_supervisor._ready_file
        engine_supervisor._engine_process = None
        engine_supervisor._engine_pid = None
        engine_supervisor._stop_file = None
        engine_supervisor._ready_file = None

    def tearDown(self):
        engine_supervisor._engine_process = self.original_process
        engine_supervisor._engine_pid = self.original_engine_pid
        engine_supervisor._stop_file = self.original_stop_file
        engine_supervisor._ready_file = self.original_ready_file

    def test_start_and_stop_uses_one_managed_engine_process(self):
        process = FakeProcess()
        engine_pid = 8765

        def start_process(command, **options):
            Path(options["env"]["CHRONOS_READY_FILE"]).write_text(
                str(engine_pid),
                encoding="ascii",
            )
            return process

        with (
            patch.object(
                engine_supervisor,
                "read_engine_status",
                side_effect=[
                    {"status": "stopped"},
                    {"status": "running", "pid": engine_pid},
                ],
            ),
            patch.object(
                engine_supervisor.subprocess,
                "Popen",
                side_effect=start_process,
            ),
            patch.object(engine_supervisor.time, "sleep"),
        ):
            result = engine_supervisor.start_engine()
            self.assertEqual(result, {"started": True, "pid": engine_pid})
            self.assertEqual(
                engine_supervisor.start_engine(),
                {"started": False, "pid": engine_pid},
            )

            stop_result = engine_supervisor.stop_engine()

        self.assertEqual(stop_result, {"stopped": True})
        self.assertEqual(process.wait_timeout, 10)
        self.assertIsNone(engine_supervisor._engine_process)
        self.assertIsNone(engine_supervisor._engine_pid)
        self.assertIsNone(engine_supervisor._stop_file)
        self.assertIsNone(engine_supervisor._ready_file)

    def test_start_clears_files_from_an_exited_managed_process(self):
        process = FakeProcess()
        process.running = False
        engine_pid = 8765

        with tempfile.TemporaryDirectory() as temp_dir:
            stop_file = Path(temp_dir) / "old-stop"
            ready_file = Path(temp_dir) / "old-ready"
            stop_file.touch()
            ready_file.touch()
            engine_supervisor._engine_process = process
            engine_supervisor._stop_file = stop_file
            engine_supervisor._ready_file = ready_file

            new_process = FakeProcess()

            def start_process(command, **options):
                Path(options["env"]["CHRONOS_READY_FILE"]).write_text(
                    str(engine_pid),
                    encoding="ascii",
                )
                return new_process

            with (
                patch.object(
                    engine_supervisor,
                    "read_engine_status",
                    side_effect=[
                        {"status": "stopped"},
                        {"status": "running", "pid": engine_pid},
                    ],
                ),
                patch.object(
                    engine_supervisor.subprocess,
                    "Popen",
                    side_effect=start_process,
                ),
                patch.object(engine_supervisor.time, "sleep"),
            ):
                result = engine_supervisor.start_engine()
                self.assertEqual(
                    result,
                    {"started": True, "pid": engine_pid},
                )
                self.assertFalse(stop_file.exists())
                self.assertFalse(ready_file.exists())
                engine_supervisor.stop_engine()

    def test_existing_running_engine_is_not_started_twice(self):
        with (
            patch.object(
                engine_supervisor,
                "read_engine_status",
                return_value={"status": "running", "pid": 4321},
            ),
            patch.object(
                engine_supervisor,
                "_process_is_running",
                return_value=True,
            ),
            patch.object(engine_supervisor.subprocess, "Popen") as popen,
        ):
            result = engine_supervisor.start_engine()

        self.assertEqual(result, {"started": False, "pid": 4321})
        popen.assert_not_called()

    def test_external_engine_cannot_be_stopped_by_this_dashboard(self):
        with patch.object(
            engine_supervisor,
            "read_engine_status",
            return_value={"status": "running", "pid": 4321},
        ):
            with self.assertRaisesRegex(RuntimeError, "did not start"):
                engine_supervisor.stop_engine()


if __name__ == "__main__":
    unittest.main()
