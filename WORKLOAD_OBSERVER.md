# Read-only Linux workload observations

`workload_observer.py` adds a dependency-free, bounded observation path. It does
not install anything, contact a gateway, reserve memory, alter cgroups, or start,
pause, restart, or terminate processes. Nothing is deployed by running it.

```sh
python workload_observer.py
python workload_observer.py --demo --items 3
python -m unittest discover -s tests -p 'test_workload_observer.py' -v
```

The first command reads one live snapshot and prints JSON. The second performs
three real 4 KiB file writes in its own temporary directory, flushes them, verifies
each artifact through a separate read and SHA-256 comparison, and samples memory
after every verified item. It removes the directory before returning. Its progress
sequence counts verified artifacts, never heartbeats. This same-process demo is
small, finite and **not governed by the memory decision engine**. It is not an
OOM, recovery, crash-durability, deployment, or production safety test.

## Data and uncertainty

- Host data comes from `/proc/meminfo`: `MemTotal` and `MemAvailable`, converted
  from Linux kB units to bytes. `MemFree` is not an acceptable replacement.
- Current-process cgroup v2 membership and its covering mount come from
  `/proc/self/cgroup` and `/proc/self/mountinfo`; paths are not guessed.
- `memory.current` and `memory.max` are read for the leaf and every visible
  ancestor through the mount root. Each ancestor remains separately visible in
  the JSON. Explicit `max` means unlimited at that level; absence does not.
- With valid data, reported headroom is the minimum of host `MemAvailable` and
  each finite ancestor's `max(0, memory.max - memory.current)`. Reported total is
  the minimum of host total and finite ancestor limits. These are observations
  of **visible limits**, not reservations or guaranteed allocatable memory.
- Missing, unreadable, oversized, malformed or contradictory required data,
  changed cgroup membership/mounts, and unsupported platforms produce `unknown`
  with null combined bytes. Available host data is preserved separately. No old
  reading is reused. A zero visible capacity also remains unusable/unknown.
- Kernel-root memory interfaces can legitimately be absent. This collector
  deliberately still reports combined headroom as unknown rather than assuming
  unlimited capacity. Cgroup v1 is unsupported. In particular, an environment
  exposing meminfo without a cgroup mount produces real host evidence and unknown
  combined headroom.

Live observations carry `synthetic: false`. An explicitly substituted `proc_root`
is labeled `synthetic: true` for deterministic fixtures. The demo's actual file
work is non-synthetic; each nested memory reading retains its own provenance.

## Explicit engine adapter

```python
from workload_observer import LinuxMemoryObserver, submit_memory_observation

observation = LinuxMemoryObserver().collect()
accepted = submit_memory_observation(engine, observation)
```

The adapter invokes only the existing
`observe_memory(observed_at, available_bytes, total_bytes)` interface. Unknown
observations are forwarded with null bytes to clear earlier usable evidence.
Keep the full JSON observation separately when provenance matters: the legacy
three-value interface cannot retain the host/cgroup breakdown or synthetic flag.
Recording a sample does not authorize a real operation or make a synthetic engine
real. The caller must use the same wall-clock domain as the engine, enforce
freshness, and independently establish permission and workload identity.

## Bounds and limits

Reads are capped at 128 KiB for meminfo, 16 KiB for membership, 512 KiB for
mountinfo, and 128 bytes for each counter. At most 64 ancestor levels are read.
Devices and FIFOs are rejected; final-component symlinks are rejected where the
platform supports `O_NOFOLLOW`. Normal operation reads only Linux procfs/cgroup
interfaces. Fixture roots are trusted test inputs, not an untrusted-path sandbox.
The demo accepts at most 16 items and 64 KiB per item through its Python API; the
CLI fixes each item at 4 KiB. It does not allocate a stress workload.

Kernel file reads are not an atomic snapshot or a hard wall-time guarantee.
Namespaces can hide ancestor limits, unrelated work can consume memory
immediately, and `memory.high`, swap, NUMA, hugepages, CPU pressure and allocation
failure modes are not modeled. The observer measures its own process environment;
it does not establish that another worker has the same cgroup. Verified file
progress demonstrates this tiny workload only, not semantic success elsewhere.
All output explicitly states that no safety guarantee is established.

Kernel references: [cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html)
and [procfs memory fields](https://docs.kernel.org/filesystems/proc.html).
