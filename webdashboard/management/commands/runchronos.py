import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Command(BaseCommand):
    help = "Run ChronosMatch's engine and Django dashboard together."

    def add_arguments(self, parser):
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--port", default="8000")

    def handle(self, *args, **options):
        stop_file = Path(tempfile.gettempdir()) / (
            f"chronosmatch_stop_{os.getpid()}"
        )
        stop_file.unlink(missing_ok=True)
        command = [
            sys.executable,
            "-u",
            "-m",
            "ipc.engine_core",
        ]
        process_environment = os.environ.copy()
        process_environment["CHRONOS_STOP_FILE"] = str(stop_file)
        process_options = {
            "cwd": PROJECT_ROOT,
            "env": process_environment,
        }
        if sys.platform == "win32":
            process_options["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            process_options["start_new_session"] = True

        engine = subprocess.Popen(command, **process_options)
        self.stdout.write(
            self.style.SUCCESS(
                f"Started matching engine (PID {engine.pid})."
            )
        )

        try:
            time.sleep(0.25)
            if engine.poll() is not None:
                raise CommandError(
                    "The matching engine exited during startup. "
                    "Check Cython build, shared buffer, and console output."
                )
            call_command(
                "runserver",
                f"{options['host']}:{options['port']}",
                use_reloader=False,
            )
        finally:
            if engine.poll() is None:
                try:
                    stop_file.touch()
                    engine.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    engine.terminate()
                    engine.wait(timeout=5)
                finally:
                    stop_file.unlink(missing_ok=True)
