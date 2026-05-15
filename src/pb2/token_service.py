"""Narrow expiring approval tokens for PB-2 durable waits."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import timedelta
from typing import Any

from src.pb2.schemas import utc_now


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _json_b64(payload: dict[str, Any]) -> str:
    return _b64url(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _decode_part(part: str) -> dict[str, Any]:
    padding = "=" * (-len(part) % 4)
    return json.loads(base64.urlsafe_b64decode(f"{part}{padding}"))


class ApprovalTokenService:
    """Small HS256 JWT service without third-party dependencies.

    Swap this for python-jose once the virtualenv installs all requirements.
    The claims already match the roadmap: workflow, branch, action class,
    operator, expiry, rollback pointer, and single action scope.
    """

    def __init__(self, secret: str | None = None) -> None:
        self._secret = (secret or os.getenv("AWCP_APPROVAL_SECRET") or "awcp-dev-secret").encode("utf-8")

    def issue(
        self,
        *,
        approval_id: str,
        workflow_id: str,
        branch_id: str,
        action_class: str,
        requested_scope: str,
        rollback_pointer: str,
        operator: str,
        ttl_minutes: int = 10,
    ) -> str:
        """Issue a workflow-scoped, branch-scoped, expiring approval token."""

        now = utc_now()
        payload = {
            "sub": approval_id,
            "workflow_id": workflow_id,
            "branch_id": branch_id,
            "action_class": action_class,
            "requested_scope": requested_scope,
            "rollback_pointer": rollback_pointer,
            "operator": operator,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=ttl_minutes)).timestamp()),
        }
        header = {"alg": "HS256", "typ": "JWT"}
        signing_input = f"{_json_b64(header)}.{_json_b64(payload)}"
        signature = hmac.new(self._secret, signing_input.encode("ascii"), hashlib.sha256).digest()
        return f"{signing_input}.{_b64url(signature)}"

    def verify(self, token: str, expected: dict[str, str]) -> dict[str, Any]:
        """Verify signature, expiry, and expected workflow/action claims."""

        try:
            header_part, payload_part, signature_part = token.split(".")
        except ValueError as exc:
            raise ValueError("Malformed approval token.") from exc

        signing_input = f"{header_part}.{payload_part}"
        expected_signature = _b64url(
            hmac.new(self._secret, signing_input.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(expected_signature, signature_part):
            raise ValueError("Invalid approval token signature.")

        payload = _decode_part(payload_part)
        if int(utc_now().timestamp()) >= int(payload["exp"]):
            raise ValueError("Approval token has expired.")

        for claim, expected_value in expected.items():
            if payload.get(claim) != expected_value:
                raise ValueError(f"Approval token claim mismatch for {claim}.")

        return payload
