import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "smol-toml";
import { config as appConfig } from "../functions/app.mjs";
import { config as cronConfig } from "../functions/cron.mjs";
import { config as workerConfig } from "../functions/worker-background.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const toml = parse(fs.readFileSync(path.join(root, "netlify.toml"), "utf8"));

test("static publish and function routing preserve the original app surface", () => {
  assert.equal(toml.build.publish, "dist");
  assert.equal(toml.build.functions, "netlify/functions");
  assert.deepEqual(appConfig.path, ["/", "/*"]);
  assert.deepEqual(appConfig.excludedPath, ["/static/*"]);
  assert.equal(appConfig.preferStatic, true);
});

test("scheduled and background contracts are explicit", () => {
  assert.equal(cronConfig.schedule, "* * * * *");
  assert.equal(workerConfig.background, true);
  assert.equal(toml.functions.cron.node_bundler, "none");
});

test("function bundles include the app but exclude secrets and ephemeral storage", () => {
  for (const name of ["app", "worker-background"]) {
    const included = toml.functions[name].included_files;
    assert.ok(included.includes("app/**"));
    assert.ok(included.includes("database/**"));
    assert.ok(included.includes("netlify/python-runtime/**"));
    assert.ok(included.includes("netlify/python-packages/**"));
    assert.ok(included.includes("!app/config/*.env"));
    assert.ok(included.includes("!app/storage/**"));
    assert.ok(included.includes("!**/__pycache__/**"));
  }
});

test("package scripts and Node engine match the deployment contract", () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8"));
  assert.equal(pkg.type, "module");
  assert.equal(pkg.engines.node, ">=22.11.0 <25");
  assert.equal(pkg.scripts.build, "node netlify/build.mjs");
  assert.equal(pkg.scripts["db:initialize"], "node netlify/initialize.mjs");
  assert.ok(pkg.scripts.check.includes("node --test netlify/tests/*.test.mjs"));
});
