#!/usr/bin/env node
"use strict";

// Thin launcher: runs the bundled scripts/ucf_rs.py with the user's Python.
// All behavior lives in the Python script. This file only finds a Python
// (3.10+), starts it without a shell, and passes the exit code through.

const { spawn, spawnSync } = require("node:child_process");
const path = require("node:path");

const SCRIPT = path.join(__dirname, "..", "scripts", "ucf_rs.py");
const PROBE = "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)";
// Not a UCF-RS exit code (those are 0, 1, 2), so callers can tell "Python not
// found" apart from "UCF-RS reported a problem". 127 is the shell convention
// for "command not found".
const EXIT_NO_PYTHON = 127;

function candidates(env, platform) {
  if (env.UCF_RS_PYTHON) {
    return [{ command: env.UCF_RS_PYTHON, args: [], label: "UCF_RS_PYTHON" }];
  }
  if (platform === "win32") {
    return [
      { command: "py", args: ["-3"], label: "py -3" },
      { command: "python", args: [], label: "python" },
    ];
  }
  return [
    { command: "python3", args: [], label: "python3" },
    { command: "python", args: [], label: "python" },
  ];
}

function isUsable(candidate) {
  const result = spawnSync(candidate.command, [...candidate.args, "-c", PROBE], {
    stdio: "ignore",
    windowsHide: true,
    timeout: 15000,
  });
  return !result.error && result.status === 0;
}

function findPython(env = process.env, platform = process.platform) {
  const list = candidates(env, platform);
  const found = list.find(isUsable);
  return { found, tried: list.map((item) => item.label) };
}

function noPythonMessage(tried, env) {
  const lines = ["ucf-rs: could not find Python 3.10 or newer."];
  if (env.UCF_RS_PYTHON) {
    lines.push(`UCF_RS_PYTHON is set to ${JSON.stringify(env.UCF_RS_PYTHON)}, but that is not a working Python 3.10+.`);
  } else {
    lines.push(`Tried: ${tried.join(", ")}.`);
    lines.push("Install Python 3.10+ from https://www.python.org/downloads/, or set UCF_RS_PYTHON to its full path.");
  }
  return lines.join("\n");
}

function main() {
  const { found, tried } = findPython();
  if (!found) {
    process.stderr.write(noPythonMessage(tried, process.env) + "\n");
    return EXIT_NO_PYTHON;
  }
  const child = spawn(found.command, [...found.args, SCRIPT, ...process.argv.slice(2)], {
    stdio: "inherit",
    windowsHide: true,
  });
  child.on("error", (error) => {
    process.stderr.write(`ucf-rs: failed to start ${found.label}: ${error.message}\n`);
    process.exit(EXIT_NO_PYTHON);
  });
  // Ctrl+C already reaches the child through the terminal, so SIGINT is not
  // forwarded (that would interrupt Python twice). SIGTERM and SIGHUP are.
  for (const signal of ["SIGTERM", "SIGHUP"]) {
    process.on(signal, () => child.kill(signal));
  }
  process.on("SIGINT", () => {});
  child.on("exit", (code, signal) => {
    if (signal) {
      process.removeAllListeners(signal);
      process.kill(process.pid, signal);
      return;
    }
    process.exit(code === null ? 1 : code);
  });
  return null;
}

if (require.main === module) {
  const code = main();
  if (code !== null) {
    process.exit(code);
  }
} else {
  module.exports = { candidates, findPython, noPythonMessage, EXIT_NO_PYTHON };
}
