"""
Python SDK for Bank of Ireland Open Banking AISP
(local sandbox or real https://api-sandbox.bankofireland.com)

Local usage is zero-config. Real sandbox still requires TPP registration + certificates.
"""
from typing import Any, Dict, List, Optional
import requests
import uuid
from datetime import datetime, timezone, timedelta


class BankOfIrelandClient:
    def __init__(
        self,
        base_url: str = "http://localhost:3004",
        financial_id: str = "0015800000jfQ9aAAE",
        timeout: float = 15.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.financial_id = financial_id
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-fapi-financial-id": financial_id,
        })
        self.access_token: Optional[str] = None

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _headers(self) -> Dict[str, str]:
        h = {
            "x-fapi-interaction-id": str(uuid.uuid4()),
            "x-fapi-auth-date": datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT"),
        }
        if self.access_token:
            h["Authorization"] = f"Bearer {self.access_token}"
        return h

    def _req(self, method: str, path: str, **kwargs) -> Any:
        headers = self._headers()
        headers.update(kwargs.pop("headers", {}))
        r = self.session.request(
            method, self._url(path), headers=headers, timeout=self.timeout, **kwargs
        )
        r.raise_for_status()
        return r.json() if r.content else None

    # ---------- Auth ----------
    def get_token(self, client_id: str = "sandbox", client_secret: str = "sandbox") -> str:
        """Obtain a client_credentials access token (local sandbox accepts anything)."""
        data = self._req(
            "POST",
            "oauth/as/token.oauth2",
            data={"grant_type": "client_credentials", "scope": "accounts"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.access_token = data["access_token"]
        return self.access_token

    def use_sandbox_token(self):
        """Quick path: use the well-known local test token."""
        self.access_token = "sandbox-token"

    # ---------- Consents ----------
    def create_account_access_consent(
        self,
        permissions: Optional[List[str]] = None,
        expiration_days: int = 90,
        transaction_from: Optional[str] = None,
        transaction_to: Optional[str] = None,
    ) -> Dict:
        if permissions is None:
            permissions = [
                "ReadAccountsBasic",
                "ReadAccountsDetail",
                "ReadBalances",
                "ReadTransactionsCredits",
                "ReadTransactionsDebits",
                "ReadTransactionsDetail",
            ]
        now = datetime.now(timezone.utc)
        body = {
            "Data": {
                "Permissions": permissions,
                "ExpirationDateTime": (now + timedelta(days=expiration_days)).strftime(
                    "%Y-%m-%dT%H:%M:%S+00:00"
                ),
            },
            "Risk": {},
        }
        if transaction_from:
            body["Data"]["TransactionFromDateTime"] = transaction_from
        if transaction_to:
            body["Data"]["TransactionToDateTime"] = transaction_to

        return self._req(
            "POST",
            "1/api/open-banking/v3.0/aisp/account-access-consents",
            json=body,
        )

    def get_consent(self, consent_id: str) -> Dict:
        return self._req(
            "GET",
            f"1/api/open-banking/v3.0/aisp/account-access-consents/{consent_id}",
        )

    def authorise_consent(self, consent_id: str) -> Dict:
        """Local-only helper that flips the consent to Authorised."""
        return self._req(
            "POST",
            f"1/api/open-banking/v3.0/aisp/account-access-consents/{consent_id}/authorise",
            json={},
        )

    # ---------- Accounts ----------
    def get_accounts(self) -> Dict:
        return self._req("GET", "1/api/open-banking/v3.0/aisp/accounts")

    def get_account(self, account_id: str) -> Dict:
        return self._req("GET", f"1/api/open-banking/v3.0/aisp/accounts/{account_id}")

    def get_balances(self, account_id: str) -> Dict:
        return self._req(
            "GET", f"1/api/open-banking/v3.0/aisp/accounts/{account_id}/balances"
        )

    def get_transactions(self, account_id: str) -> Dict:
        return self._req(
            "GET", f"1/api/open-banking/v3.0/aisp/accounts/{account_id}/transactions"
        )

    # ---------- Convenience ----------
    def full_flow_demo(self) -> Dict:
        """Run a complete local happy-path: token → consent → authorise → accounts → balances."""
        self.use_sandbox_token()
        consent = self.create_account_access_consent()
        consent_id = consent["Data"]["ConsentId"]
        self.authorise_consent(consent_id)
        accounts = self.get_accounts()
        account_id = accounts["Data"]["Account"][0]["AccountId"]
        balances = self.get_balances(account_id)
        txs = self.get_transactions(account_id)
        return {
            "consent_id": consent_id,
            "accounts": accounts,
            "balances": balances,
            "transactions": txs,
        }
