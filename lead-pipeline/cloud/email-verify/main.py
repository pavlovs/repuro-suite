"""Google Cloud Function: Email verification via Abstract API proxy.

Accepts GET ?email=user@domain.com
Returns JSON {"email": "...", "valid": true/false, "smtp_valid": true/false, "error": null/"reason"}

Proxies through Abstract API which performs SMTP verification from their
non-PBL-listed servers (GCP blocks outbound port 25/587).
"""

import json
import os
import functions_framework
import requests


ABSTRACT_API_KEY = os.environ.get("ABSTRACT_API_KEY", "")
ABSTRACT_URL = "https://emailvalidation.abstractapi.com/v1/"


def _check_email(email: str) -> tuple[bool, bool, str | None]:
    """Check email via Abstract API. Returns (is_deliverable, smtp_valid, error)."""
    if not ABSTRACT_API_KEY:
        return False, False, "ABSTRACT_API_KEY not configured"

    try:
        resp = requests.get(
            ABSTRACT_URL,
            params={"api_key": ABSTRACT_API_KEY, "email": email},
            timeout=30,
        )
        if resp.status_code != 200:
            return False, False, f"API error: {resp.status_code}"

        data = resp.json()
        deliverable = data.get("deliverability") == "DELIVERABLE"
        smtp_info = data.get("is_smtp_valid", {})
        smtp_valid = (
            smtp_info.get("value", False)
            if isinstance(smtp_info, dict)
            else bool(smtp_info)
        )

        return deliverable, smtp_valid, None
    except Exception as e:
        return False, False, f"API call failed: {e}"


@functions_framework.http
def verify_email(request):
    """HTTP Cloud Function entry point."""
    if request.method == "OPTIONS":
        return (
            "",
            204,
            {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET",
                "Access-Control-Max-Age": "3600",
            },
        )

    email = request.args.get("email", "").strip()
    if not email or "@" not in email:
        return json.dumps(
            {"email": email, "valid": False, "error": "invalid email format"}
        ), 400

    deliverable, smtp_valid, error = _check_email(email)
    return json.dumps(
        {
            "email": email,
            "valid": deliverable and smtp_valid,
            "smtp_valid": smtp_valid,
            "deliverable": deliverable,
            "error": error,
        }
    ), 200
