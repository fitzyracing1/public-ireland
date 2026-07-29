#!/usr/bin/env python3
"""
Bank of Ireland Open Banking AISP local sandbox simulator.
Mimics the structure of https://api-sandbox.bankofireland.com/1/api/open-banking/v3.0/aisp
and the OBIE Account Information Services APIs.

Real BoI sandbox requires TPP registration + certificates.
This local version needs none of that — perfect for offline development & unit tests.
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.parse
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
import secrets

SEED_PATH = Path(__file__).parent / "data" / "seed.json"
PORT = 3004
FINANCIAL_ID = "0015800000jfQ9aAAE"  # BoI sandbox fapi-financial-id

class BoIHandler(BaseHTTPRequestHandler):
    seed = None
    consents = {}          # ConsentId -> consent dict
    tokens = set()         # simple bearer tokens

    def _load(self):
        if BoIHandler.seed is None:
            with open(SEED_PATH) as f:
                BoIHandler.seed = json.load(f)
        return BoIHandler.seed

    def _now(self):
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    def _send(self, code, data=None, headers=None):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers",
                         "Content-Type, Authorization, x-fapi-financial-id, "
                         "x-fapi-interaction-id, x-fapi-auth-date, x-fapi-customer-ip-address")
        self.send_header("x-fapi-interaction-id",
                         self.headers.get("x-fapi-interaction-id", str(uuid.uuid4())))
        if headers:
            for k, v in headers.items():
                self.send_header(k, v)
        self.end_headers()
        if data is not None:
            self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def do_OPTIONS(self):
        self._send(204)

    def _auth_ok(self):
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:].strip()
            return token in BoIHandler.tokens or token == "sandbox-token"
        return False

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._send(400, {"Code": "UK.OBIE.Field.Invalid", "Message": "Invalid JSON"})
            return

        path = urllib.parse.urlparse(self.path).path.rstrip("/")

        # ---- Token endpoint (simplified client_credentials) ----
        if path.endswith("/oauth/as/token.oauth2") or path.endswith("/token"):
            token = secrets.token_urlsafe(24)
            BoIHandler.tokens.add(token)
            self._send(200, {
                "access_token": token,
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "accounts openid"
            })
            return

        # ---- Create Account Access Consent ----
        if path.endswith("/account-access-consents") or path.endswith("/account-access-consents/"):
            if not self._auth_ok():
                self._send(401, {"Code": "UK.OBIE.Unauthorized", "Message": "Missing or invalid token"})
                return

            data = payload.get("Data", {})
            consent_id = str(uuid.uuid4())
            now = self._now()
            consent = {
                "Data": {
                    "ConsentId": consent_id,
                    "CreationDateTime": now,
                    "Status": "AwaitingAuthorisation",
                    "StatusUpdateDateTime": now,
                    "Permissions": data.get("Permissions", [
                        "ReadAccountsBasic", "ReadAccountsDetail",
                        "ReadBalances", "ReadTransactionsDetail"
                    ]),
                    "ExpirationDateTime": data.get("ExpirationDateTime",
                        (datetime.now(timezone.utc) + timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%S+00:00")),
                    "TransactionFromDateTime": data.get("TransactionFromDateTime"),
                    "TransactionToDateTime": data.get("TransactionToDateTime")
                },
                "Risk": payload.get("Risk", {}),
                "Links": {
                    "Self": f"http://localhost:{PORT}/1/api/open-banking/v3.0/aisp/account-access-consents/{consent_id}"
                },
                "Meta": {}
            }
            BoIHandler.consents[consent_id] = consent
            self._send(201, consent)
            return

        # ---- Fake authorise endpoint (local helper) ----
        if path.endswith("/authorise") or "/consents/" in path and path.endswith("/authorise"):
            consent_id = path.split("/")[-2] if "/consents/" in path else payload.get("ConsentId")
            if consent_id in BoIHandler.consents:
                BoIHandler.consents[consent_id]["Data"]["Status"] = "Authorised"
                BoIHandler.consents[consent_id]["Data"]["StatusUpdateDateTime"] = self._now()
                self._send(200, {"Status": "Authorised", "ConsentId": consent_id})
            else:
                self._send(404, {"Message": "Consent not found"})
            return

        self._send(404, {"Message": "Not found"})

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path.rstrip("/")
        seed = self._load()

        if path in ("", "/", "/1/api/open-banking/v3.0/aisp"):
            self._send(200, {
                "message": "Bank of Ireland Open Banking AISP local sandbox",
                "real_sandbox": "https://api-sandbox.bankofireland.com/1/api/open-banking/v3.0/aisp",
                "developer_hub": "https://developer.bankofireland.com/",
                "note": "This is a local simulator. Real BoI requires TPP registration + certificates.",
                "endpoints": [
                    "POST /oauth/as/token.oauth2",
                    "POST /account-access-consents",
                    "GET  /account-access-consents/{ConsentId}",
                    "POST /account-access-consents/{ConsentId}/authorise  (local helper)",
                    "GET  /accounts",
                    "GET  /accounts/{AccountId}",
                    "GET  /accounts/{AccountId}/balances",
                    "GET  /accounts/{AccountId}/transactions"
                ]
            })
            return

        if not self._auth_ok() and "/token" not in path:
            self._send(401, {"Code": "UK.OBIE.Unauthorized", "Message": "Missing or invalid token. Call /token first or use Bearer sandbox-token"})
            return

        if "/account-access-consents/" in path:
            consent_id = path.split("/")[-1]
            if consent_id in BoIHandler.consents:
                self._send(200, BoIHandler.consents[consent_id])
            else:
                self._send(404, {"Code": "UK.OBIE.Resource.NotFound", "Message": "Consent not found"})
            return

        if path.endswith("/accounts"):
            self._send(200, {
                "Data": {"Account": seed["accounts"]},
                "Links": {"Self": f"http://localhost:{PORT}/1/api/open-banking/v3.0/aisp/accounts"},
                "Meta": {"TotalPages": 1}
            })
            return

        if "/accounts/" in path and not path.endswith(("/balances", "/transactions")):
            account_id = path.split("/")[-1]
            acc = next((a for a in seed["accounts"] if a["AccountId"] == account_id), None)
            if acc:
                self._send(200, {
                    "Data": {"Account": [acc]},
                    "Links": {"Self": f"http://localhost:{PORT}/1/api/open-banking/v3.0/aisp/accounts/{account_id}"},
                    "Meta": {}
                })
            else:
                self._send(404, {"Code": "UK.OBIE.Resource.NotFound", "Message": "Account not found"})
            return

        if path.endswith("/balances"):
            account_id = path.split("/")[-2]
            bals = seed["balances"].get(account_id, [])
            self._send(200, {
                "Data": {"Balance": bals},
                "Links": {"Self": f"http://localhost:{PORT}/1/api/open-banking/v3.0/aisp/accounts/{account_id}/balances"},
                "Meta": {}
            })
            return

        if path.endswith("/transactions"):
            account_id = path.split("/")[-2]
            txs = seed["transactions"].get(account_id, [])
            self._send(200, {
                "Data": {"Transaction": txs},
                "Links": {"Self": f"http://localhost:{PORT}/1/api/open-banking/v3.0/aisp/accounts/{account_id}/transactions"},
                "Meta": {}
            })
            return

        self._send(404, {"Message": "Not found"})

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {args[0]}")


def main():
    import argparse
    p = argparse.ArgumentParser(description="Bank of Ireland Open Banking local sandbox")
    p.add_argument("--port", type=int, default=PORT)
    args = p.parse_args()
    server = HTTPServer(("0.0.0.0", args.port), BoIHandler)
    print(f"Bank of Ireland AISP sandbox running at http://0.0.0.0:{args.port}")
    print(f"  Token:     POST http://localhost:{args.port}/oauth/as/token.oauth2")
    print(f"  Consents:  POST http://localhost:{args.port}/1/api/open-banking/v3.0/aisp/account-access-consents")
    print(f"  Accounts:  GET  http://localhost:{args.port}/1/api/open-banking/v3.0/aisp/accounts")
    print("  Tip: use Authorization: Bearer sandbox-token for quick tests")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down")
        server.server_close()


if __name__ == "__main__":
    main()
