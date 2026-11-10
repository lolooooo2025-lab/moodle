/* Prepare the complete application for Netlify.
 * - extracts the pinned, checksummed Linux CPython + pg_dump runtime;
 * - installs the original Python lock into a private bundle directory;
 * - removes server extras that the loopback h11/asyncio adapter does not use;
 * - copies the original static assets to the CDN publish directory;
 * - optionally runs the original idempotent DB bootstrap during the build.
 * No secret is written into dist/ or into the function bundle.
 */
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const netlify = path.join(root, "netlify");
const runtime = path.join(netlify, "python-runtime");
const packages = path.join(netlify, "python-packages");
const dist = path.join(root, "dist");
const archive = path.join(netlify, "runtime", "python-runtime.tar.gz");
const expectedSha = "659c2d81a91a346bcba9ad9b44377aa1c6e47cc9f8cfdbffc70a70a1963797e6";

function run(command, args, options = {}) {
  const result = spawnSync(command, args, { cwd: root, stdio: "inherit", ...options });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${command} exited ${result.status}`);
}

function rm(target) { fs.rmSync(target, { recursive: true, force: true }); }
function walk(dir, visit) {
  if (!fs.existsSync(dir)) return;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) { visit(full, true); walk(full, visit); }
    else visit(full, false);
  }
}
function sizeOf(dir) {
  let total = 0;
  walk(dir, (full, isDir) => { if (!isDir) total += fs.statSync(full).size; });
  return total;
}

const sha = createHash("sha256").update(fs.readFileSync(archive)).digest("hex");
if (sha !== expectedSha) throw new Error(`runtime_checksum_mismatch:${sha}`);

rm(runtime); rm(packages); rm(dist);
fs.mkdirSync(dist, { recursive: true });
run("tar", ["-xzf", archive, "-C", netlify]);
fs.chmodSync(path.join(runtime, "bin", "python3.11"), 0o755);
fs.chmodSync(path.join(runtime, "bin", "pg_dump"), 0o755);

const python = path.join(runtime, "bin", "python3.11");
const env = {
  ...process.env,
  PYTHONHOME: runtime,
  PYTHONPATH: [packages, root].join(path.delimiter),
  PYTHONNOUSERSITE: "1",
  PYTHONDONTWRITEBYTECODE: "1",
  LD_LIBRARY_PATH: path.join(runtime, "lib"),
  PATH: [path.join(runtime, "bin"), process.env.PATH || ""].join(path.delimiter),
  TT_NETLIFY: "1",
};
// pip uses its own vendored CA bundle; certifi is not installed yet.
run(python, ["-m", "pip", "install", "--disable-pip-version-check", "--no-cache-dir",
             "--no-compile", "--target", packages, "-r", path.join(root, "requirements.lock.txt")], { env });
env.SSL_CERT_FILE = path.join(packages, "certifi", "cacert.pem");

// The adapter uses h11 + asyncio. These lockfile extras are for a standalone
// uvicorn server/reloader/WebSocket transport and are not imported by the app.
const omitted = /^(pip|setuptools|pkg_resources|_distutils_hack|uvloop|watchfiles|websockets|httptools)(-|\.|$)/;
for (const entry of fs.readdirSync(packages)) {
  if (omitted.test(entry) || entry === "distutils-precedence.pth") rm(path.join(packages, entry));
}
walk(packages, (full, isDir) => {
  const base = path.basename(full);
  if (isDir && (base === "__pycache__" || base === "tests" || base === "test")) rm(full);
  else if (!isDir && (full.endsWith(".pyc") || full.endsWith(".pyo"))) rm(full);
});
// Optional native-symbol stripping; wheels remain manylinux-compatible.
if (spawnSync("strip", ["--version"], { stdio: "ignore" }).status === 0) {
  walk(packages, (full, isDir) => {
    if (!isDir && full.includes(".so")) spawnSync("strip", ["--strip-unneeded", full], { stdio: "ignore" });
  });
}
// pip/ensurepip/distutils are build-time only after dependencies are installed.
for (const name of ["ensurepip", "site-packages", "distutils", "__pycache__"]) rm(path.join(runtime, "lib", "python3.11", name));
rm(path.join(runtime, "include"));
walk(runtime, (full, isDir) => { if (isDir && path.basename(full) === "__pycache__") rm(full); });

fs.cpSync(path.join(root, "app", "static"), path.join(dist, "static"), { recursive: true });
const bundleBytes = sizeOf(runtime) + sizeOf(packages) + sizeOf(path.join(root, "app")) + sizeOf(path.join(root, "database"));
const info = {
  name: "Taleb Talta", mode: "netlify-neon", python: "3.11.14", pg_dump: "18.6",
  runtime_sha256: sha, bundle_bytes: bundleBytes,
  built_at: new Date().toISOString(),
};
fs.writeFileSync(path.join(netlify, "build-info.json"), JSON.stringify(info, null, 2) + "\n");
if (bundleBytes > 235 * 1024 * 1024) throw new Error(`bundle_too_large:${bundleBytes}`);

// If database settings are present at build time, initialise once so the first
// visitor does not pay the schema/seed cost inside a 60-second invocation.
if (process.env.TT_DATABASE_URL || process.env.DATABASE_URL || process.env.DATABASE_URL_UNPOOLED || process.env.TT_NEON_ENV_FILE) {
  run(python, [path.join(netlify, "launch.py"), "--initialize"], { env: { ...env, PYTHONPATH: [packages, root].join(path.delimiter) } });
}
console.log(`Netlify build ready: ${(bundleBytes / 1048576).toFixed(1)} MiB application bundle`);
