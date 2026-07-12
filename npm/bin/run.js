#!/usr/bin/env node
"use strict";

/**
 * @codebeacon/mcp — npx launcher for the codebeacon MCP stdio server.
 *
 * MCP clients configure `npx -y @codebeacon/mcp` as the server command and then
 * speak JSON-RPC over stdio. codebeacon itself is a Python package, so this
 * zero-dependency shim resolves a working `codebeacon` invocation on the host
 * and execs `codebeacon serve` with the user's args forwarded verbatim.
 *
 * stdout is the JSON-RPC channel — the wrapper must never write a byte to it or
 * it corrupts the protocol stream. Every diagnostic this shim emits goes to
 * stderr; the probe below discards the child's stdout for the same reason.
 */

const os = require("os");
const { spawn, spawnSync } = require("child_process");

// Candidate runners, in priority order. Each is a [command, prefixArgs] pair;
// the server launches as `command <prefixArgs...> serve <userArgs...>`.
//   1. codebeacon      — a PATH-installed console script (pip/pipx/uv): fastest,
//                        no resolver overhead.
//   2. uvx codebeacon  — uv's ephemeral run; no prior install needed.
//   3. pipx run ...    — pipx's ephemeral run; same idea, different tool.
//   4. python3 -m ...  — last resort for a site-packages/editable install that
//                        exposes the module but no console script on PATH.
const CANDIDATES = [
  ["codebeacon", []],
  ["uvx", ["codebeacon"]],
  ["pipx", ["run", "codebeacon"]],
  ["python3", ["-m", "codebeacon"]],
];

function log(msg) {
  process.stderr.write(`[codebeacon-mcp] ${msg}\n`);
}

// Cheap liveness probe: run `<candidate> --version` with all stdio discarded
// (its output must never reach the MCP stdout stream) and accept the candidate
// only on a clean exit. The timeout guards against a resolver that stalls on a
// network fetch.
function probe(command, prefixArgs) {
  let result;
  try {
    result = spawnSync(command, [...prefixArgs, "--version"], {
      stdio: "ignore",
      timeout: 30000,
    });
  } catch (_err) {
    return false;
  }
  return !result.error && result.status === 0;
}

function resolveRunner() {
  for (const [command, prefixArgs] of CANDIDATES) {
    if (probe(command, prefixArgs)) {
      return [command, prefixArgs];
    }
  }
  return null;
}

function fail() {
  log("could not find a working `codebeacon` install on this host.");
  log("Install it with one of:");
  log("  pipx install codebeacon");
  log("  uv tool install codebeacon");
  log("  pip install codebeacon");
  process.exit(1);
}

function main() {
  const userArgs = process.argv.slice(2);

  const runner = resolveRunner();
  if (!runner) {
    fail();
    return;
  }

  const [command, prefixArgs] = runner;
  const args = [...prefixArgs, "serve", ...userArgs];
  log(`launching: ${command} ${args.join(" ")}`);

  // stdio "inherit" wires the child's stdin/stdout/stderr straight to ours, so
  // the JSON-RPC bytes flow between the client and the Python server untouched.
  const child = spawn(command, args, { stdio: "inherit" });

  // Forward the client's shutdown signals so the Python server tears down
  // rather than being orphaned when npx is terminated.
  const forward = (signal) => {
    if (!child.killed) {
      child.kill(signal);
    }
  };
  process.on("SIGINT", () => forward("SIGINT"));
  process.on("SIGTERM", () => forward("SIGTERM"));
  process.on("SIGHUP", () => forward("SIGHUP"));

  child.on("error", (err) => {
    log(`failed to launch ${command}: ${err.message}`);
    process.exit(1);
  });

  // Mirror the child's exit status. A signal death maps to the 128+signum shell
  // convention; a normal exit passes the code straight through. Using
  // process.exitCode (not process.exit) lets any inherited streams flush first.
  child.on("exit", (code, signal) => {
    if (signal) {
      const signum = os.constants.signals[signal] || 0;
      process.exitCode = 128 + signum;
    } else {
      process.exitCode = code === null ? 1 : code;
    }
  });
}

main();
