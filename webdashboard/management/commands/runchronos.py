from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from ipc.engine_supervisor import start_engine, stop_engine


class Command(BaseCommand):
    help = "Run ChronosMatch's engine and Django dashboard together."

    def add_arguments(self, parser):
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--port", default="8000")

    def handle(self, *args, **options):
        try:
            engine = start_engine()
        except (OSError, RuntimeError) as error:
            raise CommandError(str(error)) from error
        action = "Started" if engine["started"] else "Engine already running"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} (PID {engine['pid']})."
            )
        )

        try:
            call_command(
                "runserver",
                f"{options['host']}:{options['port']}",
                use_reloader=False,
            )
        finally:
            if engine["started"]:
                stop_engine()
