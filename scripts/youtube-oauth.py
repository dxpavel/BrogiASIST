"""
YouTube OAuth setup — jednorázové spuštění
Výsledek: refresh_token uložený do .env
"""

import http.server
import threading
import webbrowser
import urllib.parse
import urllib.request
import json
import re
import os

CLIENT_ID = "469656228708-ni8167k79laco1skpe2d13qr0sd24rf2.apps.googleusercontent.com"
CLIENT_SECRET = "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"
REDIRECT_URI = "http://localhost:8080"
SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
ENV_FILE = os.path.join(os.path.dirname(__file__), "../.env")

auth_code = None

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK - muzete zavrit toto okno.")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Chyba - kod nenalezen.")

    def log_message(self, *args):
        pass

def get_token(code):
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code"
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def save_to_env(refresh_token):
    with open(ENV_FILE, "r") as f:
        content = f.read()
    if "YOUTUBE_REFRESH_TOKEN" in content:
        content = re.sub(r"YOUTUBE_REFRESH_TOKEN=.*", f"YOUTUBE_REFRESH_TOKEN={refresh_token}", content)
    else:
        content += f"\n# === YOUTUBE ===\nYOUTUBE_CLIENT_ID={CLIENT_ID}\nYOUTUBE_CLIENT_SECRET={CLIENT_SECRET}\nYOUTUBE_REFRESH_TOKEN={refresh_token}\n"
    with open(ENV_FILE, "w") as f:
        f.write(content)

if __name__ == "__main__":
    server = http.server.HTTPServer(("localhost", 8080), Handler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()

    url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&response_type=code"
        f"&scope={urllib.parse.quote(SCOPE)}"
        "&access_type=offline"
        "&prompt=consent"
    )
    print("Otviram browser...")
    webbrowser.open(url)

    thread.join(timeout=120)

    if not auth_code:
        print("CHYBA: Kod neprisel do 120s.")
        exit(1)

    print("Kod ziskan, ziskavam tokeny...")
    tokens = get_token(auth_code)

    if "refresh_token" not in tokens:
        print("CHYBA: refresh_token chybi v odpovedi:", tokens)
        exit(1)

    save_to_env(tokens["refresh_token"])
    print("OK — YOUTUBE_REFRESH_TOKEN ulozen do .env")
