/* Create a source ZIP suitable for GitHub upload or `netlify deploy --build`.
 * The ZIP intentionally excludes node_modules, generated bundles and secrets. */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const outDir = path.join(root, "deliverables");
fs.mkdirSync(outDir, { recursive: true });
const out = path.join(outDir, "Taleb-Talta-Netlify.zip");
fs.rmSync(out, { force: true });
const args = ["-r", out,
  "app", "database", "deploy", "docs", "netlify", "netlify.toml", "package.json", "package-lock.json",
  "requirements.lock.txt", "tools", "README.md", "run_dev.sh", "verify.sh",
  "-x", "app/storage/*", "app/config/*.env", "app/config/secrets.env", "*/__pycache__/*", "*.pyc",
  "netlify/python-runtime/*", "netlify/python-packages/*", "netlify/build-info.json", "docs/*verify.log"];
const result = spawnSync("zip", args, { cwd: root, stdio: "inherit" });
if (result.status !== 0) process.exit(result.status ?? 1);
const hash = spawnSync("sha256sum", [out], { cwd: root, encoding: "utf8" }).stdout.trim();
fs.writeFileSync(path.join(outDir, "Taleb-Talta-Netlify.sha256"), hash + "\n");
console.log(hash);
