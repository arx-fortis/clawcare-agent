# Experimental cooperative tiny-workload governor

This increment performs **actual local file work under admission checks**. It
only governs the deterministic workload it creates: one to three files, normally
4 KiB each, never more than 64 KiB each. It does not adopt a user job, control an
arbitrary process, run a gateway, or resume media transcription. It installs
nothing and makes no provider/network call or process-termination request.

## Demonstrate the integrated boundary

```sh
python cooperative_demo.py
python -m unittest discover -s tests -p test_cooperative_worker.py -v
```

The finite demo uses **simulated pressure and simulated interruption**, explicitly
labeled in its JSON. File writes, fsyncs, separate output reads/hashes, durable
checkpoints, restart reconstruction, and no-replay checks are real. It:

1. Creates its own new private temporary workload, initially paused.
2. Resumes explicitly and independently verifies the first output.
3. Injects a low-memory observation and demonstrates no next-unit write.
4. Requires distinct stable samples and recovery cooldown before another unit.
5. Raises a test exception after the last durable checkpoint but before the
   policy outcome, demonstrating a real intermediate ledger state.
6. Reconstructs the adapter, re-reads the existing output, reconciles its action
   without rewriting the output, and verifies final completion.
7. Separately feeds an actual Linux memory snapshot to a one-unit worker. If
   combined capacity is unknown, admission blocks and zero outputs are written.
8. Removes both private temporary roots before returning.

The interruption is a deterministic exception, not a killed process, power loss,
or kernel crash. The pressure observations do not consume real RAM. The demo
therefore proves these cooperative boundaries, not a real OOM prevention claim.

## Optional explicit persistent demo root

```sh
python cooperative_worker.py --root /tmp/new-clawcare-owned-demo init
python cooperative_worker.py --root /tmp/new-clawcare-owned-demo resume
python cooperative_worker.py --root /tmp/new-clawcare-owned-demo step
python cooperative_worker.py --root /tmp/new-clawcare-owned-demo status
python cooperative_worker.py --root /tmp/new-clawcare-owned-demo pause
python cooperative_worker.py --root /tmp/new-clawcare-owned-demo cancel
python cooperative_worker.py --root /tmp/new-clawcare-owned-demo reconcile
```

Initialization refuses an existing root. `step` uses real Linux observations by
default and writes at most one unit. There is no background loop. Missing cgroup
visibility or unsupported-platform observations correctly keep admission unknown;
unknown must not be replaced by host-only capacity. An unknown result in this
runtime is expected, not proof of a repaired or protected host.

Pause prevents new unit output until explicitly resumed. Cancellation is terminal
for that owned workload; resume cannot undo it. Both preserve existing output.
A bounded unit already executing inside its effect transaction finishes before a
concurrent pause/cancel transaction commits. This is cooperative boundary
cancellation, not instantaneous interruption.

Reconciliation remains available after cancellation. It may record receipts and
write a checkpoint for an already-existing independently verified output, but
never creates or replays a `.bin` unit. Thus cancellation means **no new unit
output**, not a prohibition on recording what already happened.

## Ownership, durability and verification

- A new random worker identity, exact fixture identity and immutable manifest
  hash bind the ledger to this workload. Paths and bytes come only from its
  bounded manifest; no command or external job/path can be submitted.
- Root privacy, fixture/manifest identity, owned directory layout and expected
  inventory are checked repeatedly, including at the output effect boundary.
  Root preflight happens before opening its lock or SQLite database. The main
  database and existing WAL/SHM sidecars must also remain regular, unlinked files;
  policy transactions use the same validated database boundary. Unexpected
  files, path drift, symlinks/hardlinks or checkpoint conflicts fail closed.
- A same-root OS-released lock excludes other cooperative writers. This is not a
  sandbox against hostile same-user processes or concurrent malicious filesystem
  replacement. Windows ACL enforcement still requires separate review.
- A durable unit intent precedes the policy claim; the durable claim precedes
  output. The existing three-claim lifetime budget and retry cooldown still
  apply. Ordinary successful units also consume that deliberately small budget.
- The adapter collects again immediately before the effect. In one SQLite
  transaction it rechecks admission, current mode, fault revision, fresh
  checkpoint verification and the exact claim before the bounded exclusive
  file create. A new unknown/pressure/stale sample blocks the write.
- Output creation is `O_EXCL` through Python's `xb` mode. File and directory
  fsyncs are attempted; the independent verifier separately reads the bounded
  output and checks exact size and expected manifest SHA-256.
- Per-unit checkpoint files are immutable and idempotent. Their identities and
  all previously verified outputs are rechecked before further work. Partial,
  conflicting, missing or corrupted checkpointed outputs are preserved for
  review, never overwritten, deleted or replayed automatically.
- Restart examines intents **and** already-checkpointed units whose policy
  outcomes remain pending. Existing correct bytes are reconciled without
  rewriting. Definite no-output claims can become known no-effect under the
  owned lock, then only retry within cooldown and the original finite budget.
- A new narrowly scoped policy API, `reconcile_verified_action`, accepts trusted
  independent verification from this owned adapter. It checks exact checkpoint
  identity, post-claim/post-fault freshness and quiescence assertions; it records
  an existing verified output without incrementing work, replaying or calling
  the worker recovered. New work still needs admission and remaining budget.
- Status separates recorded artifact verification, pending reconciliation and
  current checkpoint inventory integrity. `complete` is true only when every
  unit is verified, no action is pending, and the existing output/checkpoint
  inventory independently verifies now. It is not a gateway health label.

The pressure provenance and actual output-verification receipts remain separate.
The policy engine still labels its model decisions synthetic; the adapter only
executes the specifically authorized tiny demo operations, never interprets
`execute: false` as general authority to run arbitrary work.

## Verification boundary and next gates

Tests cover healthy work, unknown/low/stale admission, pressure changes at the
last effect boundary, hysteresis, pause/resume, terminal cancellation, stalled
heartbeat without productive progress, same-root exclusion, identity/path drift,
crashes around intent/claim/output/checkpoint/outcome, finite retries, absent or
corrupt saved output, explicit post-cancel reconciliation, and no false complete
label. A real Linux snapshot is tested without forcing resource availability.

Before using this approach for actual application jobs, implement and review a
specific cooperative adapter's units, peak-resource estimate, checkpoint schema,
semantic verifier, idempotency and cancellation behavior. Bind observations to
the actual worker namespace, verify authorization at its real effect, test
representative workloads and actual process/host crashes in an approved isolated
setting, and integrate the current application source. Validate Windows ACLs,
startup/reboot, migrations, retention, authenticated remote policy/revocation and
operational alerts separately. No deployment or launch-readiness claim follows
from this demonstrator.
