/* Internal verification helper only (not deployed). Netlify CLI's
 * functions:serve executes the real function bundles/routes; this loopback
 * proxy adds the CDN static directory that `netlify dev` would normally serve. */
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dist = path.join(root, "dist");
const upstream = new URL(process.env.TT_FUNCTIONS_UPSTREAM || "http://127.0.0.1:9998");
const types = { ".js": "application/javascript", ".css": "text/css", ".png": "image/png", ".svg": "image/svg+xml", ".json": "application/json", ".webmanifest": "application/manifest+json", ".woff2": "font/woff2", ".ico": "image/x-icon" };
http.createServer((req, res) => {
  const url = new URL(req.url, "http://127.0.0.1");
  if (url.pathname.startsWith("/static/")) {
    const file = path.resolve(dist, "." + url.pathname);
    if (!file.startsWith(dist + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { "Content-Type": types[path.extname(file)] || "application/octet-stream", "Cache-Control": "public, max-age=3600", "X-Content-Type-Options": "nosniff" });
    fs.createReadStream(file).pipe(res); return;
  }
  const headers = { ...req.headers, host: "127.0.0.1:8000" };
  const proxy = http.request({ hostname: upstream.hostname, port: upstream.port, path: url.pathname + url.search, method: req.method, headers }, (up) => {
    res.writeHead(up.statusCode || 502, up.headers);
    up.pipe(res);
  });
  proxy.on("error", () => { if (!res.headersSent) res.writeHead(502); res.end("proxy error"); });
  req.pipe(proxy);
}).listen(8000, "127.0.0.1", () => console.log("Internal Netlify verification proxy on 127.0.0.1:8000"));
