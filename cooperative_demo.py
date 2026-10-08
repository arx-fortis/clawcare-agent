"""Finite actual-file governor demonstration with explicitly SIMULATED pressure.

No real resource pressure, child processes, provider calls or gateway operations.
All tiny demo roots are private temporary directories removed before return.
"""
import hashlib
import json
from pathlib import Path
import tempfile

from cooperative_worker import CooperativeWorker, create_worker
from workload_observer import LinuxMemoryObserver
from workload_protection import Limits


class SimulatedInterruption(Exception):
    pass


class DemoClock:
    def __init__(self): self.now = 1000
    def __call__(self): return self.now
    def advance(self, seconds=1): self.now += seconds


class SimulatedPressure:
    def __init__(self, clock): self.clock = clock; self.available = 10_000_000
    def __call__(self):
        return {'synthetic': True, 'source': 'simulated_demo_pressure', 'status': 'observed',
                'observed_at': self.clock(), 'available_bytes': self.available, 'total_bytes': 20_000_000}


def run_demo():
    clock = DemoClock()
    pressure = SimulatedPressure(clock)
    limits = Limits(reserve_bytes=100, recovery_margin_bytes=50, cooldown_seconds=10)
    with tempfile.TemporaryDirectory(prefix='clawcare-cooperative-demo-') as temp:
        root = Path(temp) / 'governed'
        worker = create_worker(root, clock=clock, collector=pressure, limits=limits)
        worker.set_mode('RUNNING')
        first = worker.step()
        pressure.available = 16; clock.advance()
        paused = worker.step()
        pause_count = len(list((root / 'outputs').iterdir()))
        pressure.available = 10_000_000; clock.advance()
        cooling = worker.step()
        clock.advance(11)
        resumed = worker.step()
        def interrupt(phase):
            if phase == 'before_outcome':
                raise SimulatedInterruption('Test-only exception after durable checkpoint')
        worker.fault_hook = interrupt; clock.advance()
        try:
            worker.step()
        except SimulatedInterruption:
            pass
        before = {path.name: (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
                  for path in (root / 'outputs').iterdir()}
        before_reconcile = worker.status()
        worker = CooperativeWorker(root, clock=clock, collector=pressure)
        reconciliation = worker.reconcile()
        after = {path.name: (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
                 for path in (root / 'outputs').iterdir()}
        final = worker.status()
        live = LinuxMemoryObserver().collect()
        live_root = Path(temp) / 'real-observation'
        live_worker = create_worker(live_root, items=1, collector=lambda: live)
        live_worker.set_mode('RUNNING')
        live_result = live_worker.step()
        result = {'simulated_pressure': True, 'simulated_interruption': True,
                  'actual_local_output_verification': True,
                  'real_host_oom_protection_demonstrated': False,
                  'first_unit': first['status'], 'pressure_boundary': paused['status'],
                  'outputs_during_pressure': pause_count, 'cooldown_boundary': cooling['status'],
                  'resumed_unit': resumed['status'],
                  'pending_before_reconciliation': before_reconcile['reconciliation_pending'],
                  'complete_before_reconciliation': before_reconcile['complete'],
                  'reconciliation': reconciliation, 'existing_outputs_unchanged': before == after,
                  'complete_after_reconciliation': final['complete'],
                  'verified_units': sum(unit['state'] == 'VERIFIED' for unit in final['units']),
                  'live_capacity': {'synthetic': live['synthetic'], 'status': live['status'],
                      'host_status': live['host']['status'], 'governor_status': live_result['status'],
                      'outputs_written': len(list((live_root / 'outputs').iterdir()))}}
    result['temporary_roots_removed'] = True
    return result


if __name__ == '__main__':
    print(json.dumps(run_demo(), sort_keys=True, indent=2))
