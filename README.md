# Bank of Ireland Open Banking – Local Sandbox + SDK + Docker

Local simulator of Bank of Ireland’s **Account Information Services (AISP)** Open Banking APIs.

**Real BoI sandbox** (https://developer.bankofireland.com/) requires:

- TPP registration / Dynamic Client Registration
- Software Statement Assertion (SSA)
- eIDAS / OB certificates + MTLS
- OAuth2 + FAPI security profile

This local package needs **none of that**. Use it for offline development, unit tests, demos, and CI.

## Quick start (no Docker)

```bash
python mock_server.py --port 3004
```

## Python SDK

```python
from sdk import BankOfIrelandClient

client = BankOfIrelandClient("http://localhost:3004")
client.use_sandbox_token()          # or client.get_token()

# Full happy-path demo
result = client.full_flow_demo()
print(result["accounts"])
print(result["balances"])
print(result["transactions"])
```

## Endpoints

| Method | Path |
|--------|------|
| POST | `/oauth/as/token.oauth2` |
| POST | `/1/api/open-banking/v3.0/aisp/account-access-consents` |
| GET  | `/account-access-consents/{ConsentId}` |
| POST | `.../authorise` (local helper) |
| GET  | `/accounts` |
| GET  | `/accounts/{AccountId}` |
| GET  | `/accounts/{AccountId}/balances` |
| GET  | `/accounts/{AccountId}/transactions` |

## Docker

```bash
docker compose up --build
```

Port **3004**.

## Real sandbox pointers

- Developer Hub: https://developer.bankofireland.com/
- AISP base: `https://api-sandbox.bankofireland.com/1/api/open-banking/v3.0/aisp`
- Financial-id: `0015800000jfQ9aAAE`

When moving to the real environment, change only `base_url` + supply real certificates.
