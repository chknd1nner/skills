# GPT 5.4 review of Opencode Async Bridge

## Reference files
- 2026-04-03-opencode-async-bridge-design.md
- 2026-04-03-opencode-async-bridge.md

## Findings

1. The startup-failure contract is internally inconsistent, and it changes the observable behavior of the hook. The spec says startup errors are surfaced to
Claude via the deny reason so the user sees them immediately (docs/superpowers/specs/2026-04-03-opencode-async-bridge-design.md:93, docs/superpowers/specs/2026-04-03-opencode-async-bridge-design.md:99), but the later failure section says the hook exits 0 with no output and only logs/writes to stderr (docs/superpowers/specs/2026-04-03-opencode-async-bridge-design.md:172). The plan implements the silent fallback version (sys.exit(0) on ensure_server failure) (docs/superpowers/plans/2026-04-03-opencode-async-bridge.md:1195). That needs one explicit contract, otherwise the implementer and test suite will target different behavior.
2. The proposed server startup code can deadlock the long-lived opencode serve process by piping stdout/stderr and then never draining them. Both the spec and plan start the persistent server with stdout=subprocess.PIPE and stderr=subprocess.PIPE (docs/superpowers/specs/2026-04-03-opencode-async-bridge-design.md:82, docs/superpowers/plans/2026-04-03-opencode-async-bridge.md:875), while also stating the server should outlive the hook invocation (docs/superpowers/specs/2026-04-03-opencode-async-bridge-design.md:103). Once those pipes fill, the child can block on write and reviews will start failing nondeterministically. For a daemon-like child, use DEVNULL, a log file, or a drainer thread.
3. The end-to-end test plan leaks detached poller subprocesses and will make the suite flaky. The main flow unconditionally spawns a detached --poll child (docs/superpowers/plans/2026-04-03-opencode-async-bridge.md:1216), and the subprocess-based tests invoke that full path (docs/superpowers/plans/2026-04-03-opencode-
async-bridge.md:1066). In test_hook_writes_pending_status, no OPENCODE_TIMEOUT is set (docs/superpowers/plans/2026-04-03-opencode-async-bridge.md:1099), so the spawned poller will run with the default 300s timeout (docs/superpowers/plans/2026-04-03-opencode-async-bridge.md:1520) and outlive the test. You need a test-only way to suppress child spawning or to capture and join the child process.
4. The plan acknowledges the OpenCode API contract is unknown, but it does not preserve that verification in automated tests. Task 2 explicitly requires manual probing and a temporary uncommitted note (docs/superpowers/plans/2026-04-03-opencode-async-bridge.md:68), while the fake server hardcodes the assumed shapes (GET /, {"id": ...}, assistant role naming) (docs/superpowers/plans/2026-04-03-opencode-async-bridge.md:242, docs/superpowers/plans/2026-04-03-opencode-async-bridge.md:271), and the final model-override test explicitly does not verify the request body at all (docs/superpowers/plans/2026-04-03-opencode-async-bridge.md:1614). That leaves the highest-risk integration surface outside CI. The fixture should capture request paths, headers, and JSON bodies so the verified contract becomes testable and durable.

## Assumptions

I reviewed this as a design/plan review against the current hook and test setup, not as a live OpenCode API validation run. If your intended fallback UX is “silent
fallback only,” finding 1 is mostly a spec/plan mismatch; if you want user-visible startup errors, it is a functional gap as well.