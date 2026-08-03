# Security policy

## Supported versions

Security fixes are applied to the latest release line.

| Version | Supported |
|---|:---:|
| 1.1.x | Yes |
| 1.0.x | No |

## Reporting a vulnerability

Do not open a public issue for credentials, sandbox escapes, unsafe subprocess
behavior, checkpoint deserialization problems, or other exploitable findings.
Use GitHub's **Report a vulnerability** flow in the repository Security tab so
the report and any reproduction details remain private.

Include:

- the affected version or commit;
- the smallest safe reproduction;
- expected and observed behavior;
- whether files, credentials, subprocesses, or checkpoints are exposed;
- any known workaround.

## Security boundary

Agent OS applies path checks, fixed subprocess working directories, permission
modes, credential redaction, and human approval to reduce accidental damage.
These controls are not OS-level isolation. They do not contain hostile code,
network access, child processes, CPU, or memory. Run untrusted workloads in a
container or microVM and keep checkpoint databases protected as sensitive data.
