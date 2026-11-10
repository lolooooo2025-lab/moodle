/* Run the original idempotent schema/seed bootstrap using the bundled runtime. */
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const runtime = path.join(root, "netlify", "python-runtime");
const packages = path.join(root, "netlify", "python-packages");
const env = {
  ...process.env, TT_NETLIFY: "1", PYTHONHOME: runtime,
  PYTHONPATH: [packages, root].join(path.delimiter),
  LD_LIBRARY_PATH: path.join(runtime, "lib"),
  SSL_CERT_FILE: path.join(packages, "certifi", "cacert.pem"),
  PATH: [path.join(runtime, "bin"), process.env.PATH || ""].join(path.delimiter),
};
const result = spawnSync(path.join(runtime, "bin", "python3.11"), [path.join(root, "netlify", "launch.py"), "--initialize"], { cwd: root, env, stdio: "inherit" });
process.exit(result.status ?? 1);
