import { readFileSync, unlinkSync } from "node:fs";
try {
  const lock = JSON.parse(readFileSync("/tmp/tt-netlify-runtime.json", "utf8"));
  if (Number.isInteger(lock.pid)) { try { process.kill(lock.pid, "SIGTERM"); } catch {} }
  unlinkSync("/tmp/tt-netlify-runtime.json");
  console.log("Netlify local runtime stopped");
} catch { console.log("No Netlify local runtime lock found"); }
