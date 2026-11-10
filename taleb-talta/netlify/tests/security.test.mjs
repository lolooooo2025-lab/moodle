import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

function walk(dir, out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (["node_modules", ".git", ".netlify", "python-runtime", "python-packages"].includes(entry.name)) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, out);
    else out.push(full);
  }
  return out;
}

test("local secret files and generated bundles are ignored by Git", () => {
  const ignore = fs.readFileSync(path.join(root, ".gitignore"), "utf8");
  for (const pattern of ["config/*.env", "dist/", "node_modules/", ".netlify/", "netlify/python-runtime/", "netlify/python-packages/"]) {
    assert.ok(ignore.includes(pattern), `missing ignore pattern ${pattern}`);
  }
});

test("no env file is copied into the public CDN directory", () => {
  const dist = path.join(root, "dist");
  for (const file of walk(dist)) {
    assert.ok(!file.endsWith(".env"), `secret-like file in dist: ${file}`);
    assert.ok(!path.basename(file).startsWith("secrets"), `secret-like file in dist: ${file}`);
  }
});

test("adapter does not embed literal production credentials", () => {
  const files = [
    path.join(root, "netlify", "server.mjs"),
    ...fs.readdirSync(path.join(root, "netlify", "functions")).map((f) => path.join(root, "netlify", "functions", f)),
  ];
  for (const file of files) {
    const text = fs.readFileSync(file, "utf8");
    assert.ok(!/postgresql:\/\/[^\s"']+:[^\s"']+@/.test(text), `database credential in ${file}`);
    assert.ok(!/-----BEGIN [A-Z ]*PRIVATE KEY-----/.test(text), `private key in ${file}`);
  }
});
