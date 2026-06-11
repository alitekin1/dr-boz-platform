# Fix: Enable Billing/Subscription on New Server

The `billing.py` router and `payment_orders.py` model were missing from the initial deploy. Follow these steps on the new server to fix.

## Quick Fix (3 files)

```bash
cd /opt/drboz/backend/open_webui

# Download the 3 fixed files
wget -O routers/billing.py \
  https://raw.githubusercontent.com/alitekin1/dr-boz-platform/main/backend/open_webui/routers/billing.py

wget -O models/payment_orders.py \
  https://raw.githubusercontent.com/alitekin1/dr-boz-platform/main/backend/open_webui/models/payment_orders.py

wget -O main.py \
  https://raw.githubusercontent.com/alitekin1/dr-boz-platform/main/backend/open_webui/main.py

# Restart the container to load the new code
docker restart open-webui
```

## Verify it works

```bash
# Check billing endpoints inside the container
docker exec open-webui curl -s http://localhost:8080/api/v1/billing/public/plans

# Should return JSON with subscription plans like:
# [{"id":1,"name":"Free","plan_type":"free",...},{"id":2,"name":"Plus",...}]
```

## What was missing

| File | Why |
|---|---|
| `routers/billing.py` | Source was deleted, only compiled `.pyc` remained |
| `models/payment_orders.py` | Never committed, model for payment order lifecycle |
| `main.py` | Missing `import billing` and `include_router(billing)` lines |

## Billing endpoints restored

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/billing/public/plans` | None | List subscription plans from ERA DB |
| `GET` | `/api/v1/billing/public/lookup-by-phone` | None | Find user ID by phone number |
| `POST` | `/api/v1/billing/public/verify-initdata` | None | Verify Bale mini-app initData |
| `POST` | `/api/v1/billing/orders` | Bot secret | Create payment order |
| `GET` | `/api/v1/billing/orders/{id}` | Bot secret | Get order details |
| `POST` | `/api/v1/billing/orders/{id}/mark-paid` | Bot secret | Mark order paid, activate subscription |
| `POST` | `/api/v1/billing/orders/{id}/reject` | Bot secret | Reject order |
| `POST` | `/api/v1/billing/orders/{id}/cancel` | Bot secret | Cancel order |
| `POST` | `/api/v1/billing/admin/orders` | Bot admin | Admin create order |
| `GET` | `/api/v1/billing/admin/orders/pending-card` | Bot admin | List pending card-to-card payments |
| `POST` | `/api/v1/billing/admin/orders/{id}/approve` | Bot admin | Admin approve, activate subscription |
| `POST` | `/api/v1/billing/admin/orders/{id}/reject` | Bot admin | Admin reject |

## Auth

All order endpoints require `X-Bot-Secret` header matching `BOT_SHARED_SECRET` env var.
Admin endpoints additionally require `X-Bot-Admin-Id` header matching one of the IDs in `BOT_ADMIN_IDS`.

## If wget fails (GitHub auth)

You're probably not logged in since the repo is private. Clone with token instead:

```bash
git clone https://TOKEN@github.com/alitekin1/dr-boz-platform.git /tmp/drboz-fix
cp /tmp/drboz-fix/backend/open_webui/routers/billing.py /opt/drboz/backend/open_webui/routers/
cp /tmp/drboz-fix/backend/open_webui/models/payment_orders.py /opt/drboz/backend/open_webui/models/
cp /tmp/drboz-fix/backend/open_webui/main.py /opt/drboz/backend/open_webui/
rm -rf /tmp/drboz-fix
docker restart open-webui
```
