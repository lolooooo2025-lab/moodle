import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const archive = path.join(root, "netlify", "runtime", "python-runtime.tar.gz");
const expected = "659c2d81a91a346bcba9ad9b44377aa1c6e47cc9f8cfdbffc70a70a1963797e6";

test("bundled runtime archive is the pinned, checksummed artifact", () => {
  const bytes = fs.readFileSync(archive);
  assert.equal(createHash("sha256").update(bytes).digest("hex"), expected);
  assert.ok(bytes.length < 100 * 1024 * 1024);
  const build = fs.readFileSync(path.join(root, "netlify", "build.mjs"), "utf8");
  assert.ok(build.includes(expected));
});

test("Python dependency lock remains pinned", () => {
  const lock = fs.readFileSync(path.join(root, "requirements.lock.txt"), "utf8").trim().split(/\r?\n/);
  assert.ok(lock.length >= 40);
  for (const line of lock) {
    if (!line || line.startsWith("#")) continue;
    assert.match(line, /^[A-Za-z0-9_.-]+==[^\s]+$/, `unpinned dependency: ${line}`);
  }
});

test("build size guard stays below Netlify handler limit", () => {
  const build = fs.readFileSync(path.join(root, "netlify", "build.mjs"), "utf8");
  assert.ok(build.includes("235 * 1024 * 1024"));
  const infoPath = path.join(root, "netlify", "build-info.json");
  if (fs.existsSync(infoPath)) {
    const info = JSON.parse(fs.readFileSync(infoPath, "utf8"));
    assert.ok(info.bundle_bytes <= 235 * 1024 * 1024);
    assert.equal(info.runtime_sha256, expected);
  }
});
