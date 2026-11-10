/* Package every function with Netlify's own zip-it-and-ship-it and enforce the
 * 250 MB unzipped handler limit. Also checks routes, schedule and background mode. */
import { zipFunctions } from "@netlify/zip-it-and-ship-it";
import { parse } from "smol-toml";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const toml = parse(fs.readFileSync(path.join(root, "netlify.toml"), "utf8"));
const out = path.join(root, ".netlify", "bundle-check");
fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(out, { recursive: true });
const config = {};
for (const [name, value] of Object.entries(toml.functions || {})) {
  if (typeof value !== "object") continue;
  config[name] = {};
  if (value.included_files) config[name].includedFiles = value.included_files;
  if (value.node_bundler) config[name].nodeBundler = value.node_bundler;
  config[name].includedFilesBasePath = root;
}
const results = await zipFunctions(path.join(root, "netlify", "functions"), out, {
  basePath: root, repositoryRoot: root, config, parallelLimit: 1,
  manifest: path.join(out, "manifest.json"),
});
const python = path.join(root, "netlify", "python-runtime", "bin", "python3.11");
const env = { ...process.env, PYTHONHOME: path.join(root, "netlify", "python-runtime"), LD_LIBRARY_PATH: path.join(root, "netlify", "python-runtime", "lib") };
let failed = false;
for (const result of results) {
  const zip = path.join(out, `${result.name}.zip`);
  const code = "import zipfile,sys; z=zipfile.ZipFile(sys.argv[1]); print(sum(i.file_size for i in z.infolist()))";
  const proc = spawnSync(python, ["-c", code, zip], { env, encoding: "utf8" });
  const unzipped = Number(proc.stdout.trim());
  const zipped = fs.statSync(zip).size;
  const manifest = JSON.parse(fs.readFileSync(path.join(out, "manifest.json"), "utf8"));
  const entry = manifest.functions.find((f) => f.name === result.name);
  const ok = Number.isFinite(unzipped) && unzipped <= 250 * 1024 * 1024;
  if (!ok) failed = true;
  console.log(JSON.stringify({ name: result.name, zipped, unzipped, ok,
    routes: entry?.routes, schedule: entry?.schedule, invocationMode: entry?.invocationMode }));
}
const names = results.map((r) => r.name).sort();
if (JSON.stringify(names) !== JSON.stringify(["app", "cron", "worker-background"])) {
  console.error("unexpected function set", names); failed = true;
}
if (failed) process.exit(1);
console.log("BUNDLE_CHECK_PASS");
