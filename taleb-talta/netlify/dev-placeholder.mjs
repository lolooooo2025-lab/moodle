/* Netlify CLI needs a target process in custom-framework mode. All real
 * dynamic routes are handled by netlify/functions/app.mjs; static files come
 * from dist/. This placeholder never serves application data. */
import http from "node:http";
const port = Number(process.env.PORT || 9999);
http.createServer((req, res) => {
  res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
  res.end("Use the Netlify Functions route.");
}).listen(port, "0.0.0.0", () => console.log(`Netlify dev placeholder on ${port}`));
