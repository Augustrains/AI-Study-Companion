// Vite probes Windows network-drive mappings with `net use` before resolving
// modules. Some managed Windows environments prohibit Node from spawning that
// command (EPERM), even for a purely local project. No network path is used by
// this app, so report an empty mapping and let Vite use ordinary local paths.
const childProcess = require("node:child_process");

const originalExec = childProcess.exec;
childProcess.exec = function execWithoutNetworkProbe(command, ...args) {
  if (process.platform === "win32" && command === "net use") {
    const callback = [...args].reverse().find((value) => typeof value === "function");
    if (callback) queueMicrotask(() => callback(null, "", ""));
    return undefined;
  }
  return originalExec.call(this, command, ...args);
};
