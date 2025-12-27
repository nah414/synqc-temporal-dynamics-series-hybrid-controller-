# Dual-Clocking-Qubits Tooling Staging Area

This folder is reserved for the [Dual-Clocking-Qubits](https://github.com/nah414/Dual-Clocking-Qubits) toolkit so it can live alongside the SynQc Temporal Dynamics Series stack.

Because this repository is frequently used in restricted CI environments, the tooling is not automatically vendored here. Use the helper script below to fetch or update the toolkit when you have network access:

```bash
./scripts/fetch_dual_clocking_tool.sh
```

The script clones the upstream repository into this folder if it is missing, or runs `git pull` to update an existing checkout. If this folder already holds placeholder files (like this README) instead of a git checkout, the script will back them up to a timestamped directory before cloning. After pulling, follow `docs/Dual_Clocking_Qubits_Integration.md` to run the toolkit alongside the backend.
