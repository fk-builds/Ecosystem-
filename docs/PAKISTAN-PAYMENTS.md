# Payments for Pakistan (this app actually takes money)

Stripe is **not available** to a Pakistan-based business (SBP PSEFT Act 2007
licensing, no merchant account for PK companies). This app therefore ships with
three layered payment routes — and the first one works **today**, with zero
approvals:

| Mode | What it is | PKR? | Cards (USD)? | Works now? | Activation |
|------|------------|------|--------------|------------|------------|
| `manual` | Customer pays our JazzCash / EasyPaisa number or IBAN, then submits the TRX id; owner reviews and approves | ✅ | ❌ | ✅ **today** | owner click |
| `jazzcash` | JazzCash hosted DoPayment page (wallet + cards) | ✅ | PKR cards | after merchant approval (days) | callback auto |
| `paddle` | Merchant of record — international Visa/MC in USD, VAT handled, payout to you via **Payoneer** | ❌ | ✅ | after Paddle + Payoneer approval | webhook auto |
| `stripe` | Only if you later form an overseas entity | ❌ | ✅ | future | webhook auto |

`PAYMENT_PROVIDER=auto` picks in order: **paddle → jazzcash → manual → sandbox**,
using whichever credentials are configured. With an empty `.env` you land on
**manual** — that is the intended bootstrap.

---

## 1. Enable the manual route (do this first — 10 minutes)

1. Put real receiving accounts in `.env`:

   ```env
   JAZZCASH_ACCOUNT=0300-0000000
   EASYPaisa_ACCOUNT=0345-0000000
   MANUAL_BANK_NAME=Meezan Bank
   MANUAL_IBAN=PK00MEZN0000000000000000
   MANUAL_ACCOUNT_TITLE=Your Legal Name
   ```

2. Set your own admin email (the owner who reviews TRX ids):

   ```env
   ADMIN_EMAILS=you@gmail.com
   DEMO_EMAIL=demo@fk.ai      # only has admin rights if ADMIN_EMAILS is empty
   ```

3. Restart the backend. On `/billing`, “Subscribe” now shows the wallet/bank
   details and a *Transaction reference / TRX id* field. The customer pays,
   submits the TRX id → status `pending_review` → you click **Approve** on the
   same page → plan activates (Starter = Rs. 1,499/mo, Pro = Rs. 2,999/mo).

## 2. JazzCash gateway (PKR, cards + wallet) — approval takes days

Apply for a merchant account at https://payments.jazzcash.com.pk (KYC: CNIC,
bank account). You get **Merchant ID, Password, Integrity Salt**.

```env
JAZZCASH_MERCHANT_ID=MC123456
JAZZCASH_PASSWORD=yourpassword
JAZZCASH_INTEGRITY_SALT=xxxxxxxxxxxxxxxx
JAZZCASH_BASE_URL=https://payments.jazzcash.com.pk
```

Add `${PUBLIC_BASE_URL}/api/payments/jazzcash/callback` as the return URL in
the JazzCash dashboard. The backend builds the DoPayment form, verifies the
`pp_SecureHash` on callback (SHA-256 over salt + sorted field values), and
activates the plan when `pp_ResponseCode == "000"`. Amounts are sent in paisa.
Failure redirects to `/billing?status=failed`.

> Prefer PayFast or SafeSory? Both expose the same hosted-return + signature
> pattern; drop a provider in `backend/app/saas/payments/` following
> `jazzcash_provider.py`.

## 3. Paddle (international cards) — payouts to Pakistan via Payoneer

Paddle is the merchant of record: it handles EU VAT, chargebacks, invoicing —
and pays merchants in **Pakistan through Payoneer** (no USD wire fee; $100
default payout minimum).

1. Create a **Payoneer** account, then a **Paddle** account
   (https://www.paddle.com). In Paddle → Payouts, connect Payoneer.
2. In Paddle → Pricing, create 4 prices and copy their IDs:

   ```env
   PADDLE_API_KEY=pdl_live_xxxxxxxx
   PADDLE_WEBHOOK_SECRET=whsec_xxxxxxxx
   PADDLE_PRICE_STARTER_MONTHLY=pri_xxxx
   PADDLE_PRICE_STARTER_YEARLY=pri_xxxx
   PADDLE_PRICE_PRO_MONTHLY=pri_xxxx
   PADDLE_PRICE_PRO_YEARLY=pri_xxxx
   ```

3. Paddle → Developer → Webhooks: add `https://<your-domain>/api/payments/paddle/webhook`
   with events `transaction.completed`, `subscription.canceled`.
4. Restart. New checkouts redirect to Paddle; the webhook verifies the HMAC
   (`Paddle-Signature`, 5-minute skew) and activates the plan.

Paddle charges ~5% + $0.50 per transaction; price your USD plans to absorb it
(Starter $7 / Pro $15 already do).

## 4. What the backend does

- `GET /api/billing/status` → `billing_mode` (active provider), `billing_providers`
  flags, `payment_contacts`, `is_admin`.
- `POST /api/billing/checkout` `{plan, interval, provider}` → provider-specific
  result: `mode`, `order_id`, `amount_pkr`, `url`, `redirect_params`
  (JazzCash auto-POST), `instructions`, `account`.
- `POST /api/billing/payments/{id}/confirm` — customer submits TRX id →
  `pending_review`.
- `POST /api/billing/payments/{id}/approve|reject` — admin only
  (`ADMIN_EMAILS`, or demo account when empty).
- `POST /api/payments/paddle/webhook` — HMAC-verified plan activation.
- `POST /api/payments/jazzcash/callback` — hash-verified auto activation on `000`.
- `GET /api/billing/payments` — history (all for admins, own for users).

Sandbox mode is only reached when **nothing** is configured and a client asks
for it — it is labeled `sandbox (no real charge)` in the UI.

## 5. Security notes

- Manual approvals are owner-only; the TRX id is stored, never trusted.
- Paddle webhook is HMAC-SHA256 verified with a 5-minute timestamp skew.
- JazzCash callbacks are signed; a bad signature never activates a plan.
- Point `PUBLIC_BASE_URL` at your real domain, and set
  `ALLOWED_ORIGINS` to it, before going live.
