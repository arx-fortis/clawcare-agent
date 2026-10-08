"""Reuse ClawCare's existing supervisor for its opt-in synthetic fixture service."""
import argparse
import json
from pathlib import Path
import signal
import sys

from fixture_service import FixtureService
from process_lock import Busy
from supervisor import Supervisor


class FixtureSupervisor(Supervisor):
    def __init__(self, service, **kwargs):
        self.fixture_service = service
        super().__init__(str(service.database), **kwargs)

    def request_stop(self):
        self.fixture_service.revoke()
        super().request_stop()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', required=True)
    p.add_argument('command', choices=['run', 'start', 'enable', 'stop', 'status'])
    args = p.parse_args()
    service = FixtureService(args.root)
    child_python = str(Path(sys.executable).with_name('python.exe')) if Path(sys.executable).name.lower() == 'pythonw.exe' else sys.executable
    command = [child_python, str(Path(__file__).with_name('fixture_service.py').resolve()),
               '--root', str(service.root), 'run', '--managed']
    supervisor = FixtureSupervisor(service, worker_command=command)
    if args.command == 'status':
        print(json.dumps(supervisor.status(), indent=2)); return 0
    if args.command == 'stop':
        supervisor.request_stop(); return 0
    if args.command == 'enable':
        supervisor.request_start(); return 0
    if args.command == 'start':
        supervisor.request_start()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: setattr(supervisor, 'interrupted', True))
    try:
        return supervisor.run()
    except Busy:
        return 75


if __name__ == '__main__':
    sys.exit(main())
