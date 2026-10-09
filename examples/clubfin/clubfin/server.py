"""Tiny stdlib web server. The page is one HTML file with the ledger inlined."""
import http.server
import json
import os

PAGE = os.path.join(os.path.dirname(__file__), "web", "index.html")


def render(data):
    with open(PAGE, encoding="utf-8") as fh:
        html = fh.read()
    blob = json.dumps(data).replace("</", "<\\/")
    return html.replace("__DATA__", blob)


def serve(data, host="127.0.0.1", port=8000):
    body = render(data).encode("utf-8")

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    with http.server.ThreadingHTTPServer((host, port), Handler) as srv:
        print(f"ClubFin dashboard on http://{host}:{port}  (Ctrl+C to stop)")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
