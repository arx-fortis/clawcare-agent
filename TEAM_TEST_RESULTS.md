# Local multiplayer verification — 2026-09-29

Status: tested local prototype, not production capacity certification.

Command: `python -m unittest discover -s tests -p test_team_api.py -v`
Environment: Windows, Python 3.14, loopback HTTP, temporary SQLite databases,
synthetic users and fixtures. Six API test cases passed in 61.673 seconds.
The remaining handoff, repair-control, supervisor and worker suites subsequently
passed all 31 tests in 50.374 seconds: 37 passing tests across the two runs.

Observed synchronized workload:

| Check | Result |
| --- | --- |
| Distinct work-order claims by 100 clients | 100 succeeded |
| Distinct session IDs | 100 |
| Claim wave wall time | 10.834 seconds |
| Slowest claim request | 10.648 seconds |
| Subsequent simultaneous progress writes | 100 succeeded |
| Progress authors checked against issued credentials | 100 matched |
| 100 clients claiming one contested work order | 1 success, 99 conflicts |

Other passing assertions: invalid/expired credentials denied, viewer writes
denied, worker review denied, forged identity fields rejected, cross-workspace
and cross-project reads rejected, report retries deduplicated, original author
retained through another player's review, revocation persisted after service
object reconstruction, membership downgrade enforced on later requests, last
owner removal denied, and administrator privilege escalation denied.

The service was reconstructed against persisted state in one test; this is not
a host reboot or full process-crash recovery test. No actual GHL or client-sheet
data was used. No credentials or server were left intentionally running.

An earlier expanded-suite launch was blocked by Windows paging-file exhaustion.
The subsequent API run above completed. These timings reflect a bounded local
run and show material queuing latency; they are not a throughput guarantee or
evidence of unlimited multiplayer scale. Sustained-load, larger-ledger,
multi-host, identity-provider and production-security testing remain pending.
