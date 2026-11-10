/* Netlify Functions adapter for the complete FastAPI application.
 *
 * A warm Lambda container keeps one bundled CPython process alive. Each
 * invocation is proxied over loopback inside that same container; the browser
 * never talks to localhost. All application routes, templates, permissions,
 * CSRF checks and APIs remain the original Python implementation.
 */
import { spawn } from "node:child_process";
import { existsSync, readFileSync, writeFileSync, unlinkSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { randomBytes } from "node:crypto";

const here = path.dirname(fileURLToPath(import.meta.url));
let child = null;
let starting = null;
let port = 0;
let root = "";
let runtimePid = 0;
const lockPath = "/tmp/tt-netlify-runtime.json";

function readLock() {
  try {
    const lock = JSON.parse(readFileSync(lockPath, "utf8"));
    if (lock.root !== findRoot() || !Number.isInteger(lock.pid) || !Number.isInteger(lock.port)) return null;
    process.kill(lock.pid, 0);
    return lock;
  } catch { return null; }
}

async function reuseRuntime() {
  const lock = readLock();
  if (!lock) return false;
  try {
    const response = await fetch(`http://127.0.0.1:${lock.port}/healthz`, { signal: AbortSignal.timeout(800) });
    if (!response.ok) return false;
    port = lock.port; runtimePid = lock.pid; child = null;
    return true;
  } catch { return false; }
}

function findRoot() {
  const candidates = [process.env.LAMBDA_TASK_ROOT, process.cwd(), here];
  for (const candidate of candidates) {
    if (!candidate) continue;
    let dir = path.resolve(candidate);
    for (let i = 0; i < 6; i += 1) {
      if (existsSync(path.join(dir, "app", "main.py")) && existsSync(path.join(dir, "netlify", "launch.py"))) return dir;
      const parent = path.dirname(dir);
      if (parent === dir) break;
      dir = parent;
    }
  }
  throw new Error("application_bundle_missing");
}

function publicOrigin(req, context) {
  const value = process.env.TT_PUBLIC_ORIGIN || context?.site?.url || new URL(req.url).origin;
  const url = new URL(value);
  if (!["http:", "https:"].includes(url.protocol)) throw new Error("invalid_public_origin");
  return url.origin;
}

function runtimeEnv(req, context) {
  root = root || findRoot();
  const runtime = path.join(root, "netlify", "python-runtime");
  const packages = path.join(root, "netlify", "python-packages");
  const lib = path.join(runtime, "lib");
  const env = {
    ...process.env,
    TT_NETLIFY: "1",
    TT_INTERNAL_ORIGIN: process.env.TT_INTERNAL_ORIGIN || publicOrigin(req, context),
    PYTHONHOME: runtime,
    PYTHONPATH: [packages, root].join(path.delimiter),
    PYTHONNOUSERSITE: "1",
    PYTHONDONTWRITEBYTECODE: "1",
    PYTHONUNBUFFERED: "1",
    LD_LIBRARY_PATH: [lib, process.env.LD_LIBRARY_PATH || ""].filter(Boolean).join(path.delimiter),
    PATH: [path.join(runtime, "bin"), process.env.PATH || ""].filter(Boolean).join(path.delimiter),
    SSL_CERT_FILE: path.join(packages, "certifi", "cacert.pem"),
  };
  return { env, python: path.join(runtime, "bin", "python3.11") };
}

async function start(req, context) {
  if (child && child.exitCode === null && port) return;
  if (starting) return starting;
  if (await reuseRuntime()) return;
  const { env, python } = runtimeEnv(req, context);
  root = findRoot();
  const token = randomBytes(24).toString("hex");
  const proc = spawn(python, [path.join(root, "netlify", "launch.py"), "--port", "0", "--token", token], {
    cwd: root, env, stdio: ["ignore", "pipe", "pipe"], detached: true,
  });
  child = proc;
  port = 0;
  let stderrTail = "";
  proc.stderr.on("data", (block) => {
    const text = block.toString("utf8");
    stderrTail = (stderrTail + text).slice(-4000);
    // Uvicorn/application logs go to Netlify Logs. Never log request bodies.
    process.stderr.write(text);
  });
  starting = new Promise((resolve, reject) => {
    let stdout = "";
    const timer = setTimeout(() => {
      proc.kill("SIGKILL");
      reject(new Error("python_startup_timeout"));
    }, 50000);
    const fail = (error) => {
      clearTimeout(timer);
      if (child === proc) { child = null; port = 0; }
      starting = null;
      reject(error);
    };
    proc.once("error", fail);
    proc.once("exit", (code) => {
      if (child === proc) { child = null; port = 0; }
      if (!port) fail(new Error(`python_startup_exit:${code}:${stderrTail.slice(-300)}`));
    });
    proc.stdout.on("data", (block) => {
      stdout += block.toString("utf8");
      let index;
      while ((index = stdout.indexOf("\n")) !== -1) {
        const line = stdout.slice(0, index).trim();
        stdout = stdout.slice(index + 1);
        if (line.startsWith("TT_READY ")) {
          try {
            const ready = JSON.parse(line.slice(9));
            if (ready.token !== token || !Number.isInteger(ready.port)) throw new Error("bad_ready");
            port = ready.port;
            runtimePid = proc.pid;
            try { writeFileSync(lockPath, JSON.stringify({ root, pid: proc.pid, port }), { mode: 0o600 }); } catch {}
            clearTimeout(timer);
            starting = null;
            // The runtime is a loopback server reused by later invocations.
            // Do not keep a local CLI worker alive after the response ends.
            proc.unref();
            proc.stdout.unref();
            proc.stderr.unref();
            resolve();
          } catch (error) { fail(error); }
        }
      }
    });
  });
  return starting;
}

function jsonError(status, message) {
  return new Response(JSON.stringify({ success: false, message, data: null }), {
    status, headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });
}

export async function dispatch(req, context, options = {}) {
  const timeoutMs = options.timeoutMs || 300000;
  try {
    const origin = publicOrigin(req, context);
    const incoming = new URL(req.url);
    const target = new URL(incoming.pathname + incoming.search, origin);
    const headers = new Headers(req.headers);
    for (const name of ["connection", "keep-alive", "transfer-encoding", "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto"]) headers.delete(name);
    headers.set("host", target.host);
    headers.set("x-forwarded-for", context?.ip || req.headers.get("x-nf-client-connection-ip") || "127.0.0.1");
    headers.set("x-forwarded-host", target.host);
    headers.set("x-forwarded-proto", target.protocol.replace(":", ""));
    let body;
    if (!["GET", "HEAD"].includes(req.method)) {
      const bytes = Buffer.from(await req.arrayBuffer());
      if (bytes.length > 6 * 1024 * 1024) return jsonError(413, "err.upload_size");
      body = bytes;
      headers.set("content-length", String(bytes.length));
    }
    await start(req, context);
    const upstream = await fetch(`http://127.0.0.1:${port}${target.pathname}${target.search}`, {
      method: req.method, headers, body, redirect: "manual", signal: AbortSignal.timeout(timeoutMs),
    });
    const outHeaders = new Headers(upstream.headers);
    for (const name of ["connection", "keep-alive", "transfer-encoding", "server", "date"]) outHeaders.delete(name);
    const cookies = upstream.headers.getSetCookie ? upstream.headers.getSetCookie() : [];
    if (cookies.length) {
      outHeaders.delete("set-cookie");
      for (const cookie of cookies) outHeaders.append("set-cookie", cookie);
    }
    const empty = [204, 205, 304].includes(upstream.status);
    return new Response(empty ? null : upstream.body, { status: upstream.status, headers: outHeaders });
  } catch (error) {
    const code = error?.name === "TimeoutError" ? "function_timeout" : "function_unavailable";
    console.error(JSON.stringify({ event: "tt.adapter_error", code, type: error?.name || "Error" }));
    if (child) { child.kill("SIGKILL"); child = null; }
    if (runtimePid) { try { process.kill(runtimePid, "SIGKILL"); } catch {} runtimePid = 0; }
    try { unlinkSync(lockPath); } catch {}
    port = 0; starting = null;
    return jsonError(code === "function_timeout" ? 504 : 503, "err.generic");
  }
}

export function internalOrigin(req, context) { return publicOrigin(req, context); }

// The detached loopback runtime is intentionally reused across local CLI
// worker invocations and warm Lambda invocations. Use `npm run dev:stop` to
// stop it explicitly during local development.
