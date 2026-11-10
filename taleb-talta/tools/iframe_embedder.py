"""Tiny HTTPS 'shell' page used only by tools/iframe_cookie_test.py.

Top-level https://shell.test:9443 iframes the app at https://app.test:8443.
Different registrable domains => a genuine cross-site / third-party context.
Both hostnames are mapped to 127.0.0.1 by the test's host-resolver rules.
"""
import http.server
import ssl

HTML = (
    b"<!doctype html><html><head><meta charset='utf-8'></head><body>"
    b"<iframe id='f' src='https://app.test:8443/login' "
    b"style='width:1200px;height:900px;border:0'></iframe></body></html>"
)


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(HTML)))
        self.end_headers()
        self.wfile.write(HTML)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain("/tmp/tt-tls/cert.pem", "/tmp/tt-tls/key.pem")
    srv = http.server.HTTPServer(("127.0.0.1", 9443), H)
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    srv.serve_forever()
