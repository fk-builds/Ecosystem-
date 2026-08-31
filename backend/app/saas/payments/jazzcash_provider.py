"""JazzCash merchant gateway provider (PKR).

Hosted flow: we POST a DoPayment form to JazzCash; the customer pays on the
JazzCash page; JazzCash calls our callback with the transaction result, which we
verify with the secure hash and activate the plan on success (response 000).

Requires a JazzCash **merchant account** (approval takes a few days): Merchant
ID, Password and Integrity Salt, plus our callback URL. Until those env vars are
present the registry falls back to the manual provider (wallet number + review).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

from ..plans import PLANS
from .base import CheckoutResult

# Request base 64 params
_SORT_KEYS = [
    "pp_Version", "pp_TxnType", "pp_Language", "pp_MerchantID", "pp_Password",
    "pp_TxnRefNo", "pp_Amount", "pp_TxnCurrency", "pp_TxnDateTime",
    "pp_TxnExpiryDateTime", "pp_BillReference", "pp_Description", "pp_ProductID",
    "pp_ReturnURL", "ppmpf_1", "ppmpf_2", "ppmpf_3", "ppmpf_4", "ppmpf_5",
]


def jazzcash_secure_hash(salt: str, fields: dict[str, str]) -> str:
    """StringToSign = integrity_salt + '&' + values joined '&' (fields sorted)."""
    values = [str(fields[k]) for k in sorted(fields) if k in _SORT_KEYS or k.startswith("ppmpf")]
    return hashlib.sha256((salt + "&" + "&".join(values)).encode()).hexdigest().upper()


def jazzcash_default_fields(amount_pkr: int, merchant_id: str, password: str, salt: str, return_url: str, order_id: str) -> dict[str, str]:
    now = datetime.now(timezone.utc) + timedelta(hours=5)  # PKT
    expiry = now + timedelta(hours=1)
    fields: dict[str, str] = {
        "pp_Version": "1.1",
        "pp_TxnType": "MWALLET",
        "pp_Language": "EN",
        "pp_MerchantID": merchant_id,
        "pp_Password": password,
        "pp_TxnRefNo": order_id,
        "pp_Amount": str(int(amount_pkr * 100)),  # paisa
        "pp_TxnCurrency": "PKR",
        "pp_TxnDateTime": now.strftime("%Y%m%d%H%M%S"),
        "pp_TxnExpiryDateTime": expiry.strftime("%Y%m%d%H%M%S"),
        "pp_BillReference": order_id,
        "pp_Description": f"FK AI Builder {order_id}",
        "pp_ProductID": "FK-AI-BUILDER",
        "pp_ReturnURL": return_url,
        "ppmpf_1": order_id,
        "ppmpf_2": "fk",
        "ppmpf_3": "",
        "ppmpf_4": "",
        "ppmpf_5": "",
    }
    fields["pp_SecureHash"] = jazzcash_secure_hash(salt, fields)
    return fields


def verify_jazzcash_response(fields: dict[str, str], salt: str) -> bool:
    """Verify the callback/in-PN hash posted back by JazzCash."""
    if "pp_SecureHash" not in fields:
        return False
    provided = fields.pop("pp_SecureHash", "")
    expected = jazzcash_secure_hash(salt, fields)
    fields["pp_SecureHash"] = provided
    return hashlib.sha256(expected.encode()).hexdigest() == hashlib.sha256(provided.encode()).hexdigest() or expected == provided


def response_is_success(fields: dict[str, str]) -> bool:
    return str(fields.get("pp_ResponseCode", "")) == "000"


class JazzCashProvider:
    name = "jazzcash"

    def __init__(self, settings: Any):
        self.settings = settings

    @property
    def endpoint(self) -> str:
        base = self.settings.jazzcash_base_url or "https://payments.jazzcash.com.pk"
        return f"{base.rstrip('/')}/ApplicationAPI/API/Payment/DoPayment"

    async def create_checkout(
        self,
        *,
        user: dict[str, Any],
        plan_id: str,
        interval: str,
        store: Any,
        base_url: str,
    ) -> CheckoutResult:
        plan = PLANS[plan_id]
        amount_pkr = int(plan.get("price_pkr_month", 0) if interval == "month" else plan.get("price_pkr_year", 0))
        order_id = f"JZ-{uuid4().hex[:12].upper()}"
        callback = f"{base_url}/api/payments/jazzcash/callback"
        fields = jazzcash_default_fields(
            amount_pkr,
            self.settings.jazzcash_merchant_id,
            self.settings.jazzcash_password,
            self.settings.jazzcash_integrity_salt,
            callback,
            order_id,
        )
        await store.create_payment(
            user_id=user["id"],
            plan_id=plan_id,
            interval=interval,
            provider="jazzcash",
            order_id=order_id,
            amount_pkr=amount_pkr,
            currency="PKR",
            status="awaiting_payment",
            account={},
        )
        return CheckoutResult(
            mode="jazzcash",
            plan=plan_id,
            interval=interval,
            order_id=order_id,
            amount_pkr=amount_pkr,
            url=self.endpoint,
            redirect_params=fields,
            instructions="You'll be redirected to JazzCash to complete payment.",
        )


def jazzcash_callback_result(fields: dict[str, str], salt: str) -> dict[str, Any]:
    """Interpret a callback POST: {ok, order_id, error}."""
    if not verify_jazzcash_response(fields, salt):
        return {"ok": False, "order_id": fields.get("ppmpf_1") or fields.get("pp_BillReference"), "error": "invalid hash"}
    if not response_is_success(fields):
        return {"ok": False, "order_id": fields.get("ppmpf_1") or fields.get("pp_BillReference"), "error": f"jazzcash code {fields.get('pp_ResponseCode')}"}
    return {"ok": True, "order_id": fields.get("ppmpf_1") or fields.get("pp_BillReference"), "error": None}


def encode_form(params: dict[str, str]) -> str:
    return urlencode({k: v for k, v in params.items() if v != ""})
