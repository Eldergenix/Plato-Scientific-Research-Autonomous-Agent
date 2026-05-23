#!/usr/bin/env python3
"""Validate hosted Clerk/Lab deployment variables without printing secrets."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import sys
from urllib.parse import urlparse


CHECKED_KEYS = (
    "NEXT_PUBLIC_PLATO_AUTH_PROVIDER",
    "PLATO_AUTH_PROVIDER",
    "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY",
    "CLERK_SECRET_KEY",
    "PLATO_BACKEND_PROXY_SECRET",
    "PLATO_PUBLIC_ORIGIN",
    "NEXT_PUBLIC_CLERK_PROXY_URL",
    "NEXT_PUBLIC_CLERK_SIGN_IN_URL",
    "NEXT_PUBLIC_CLERK_SIGN_UP_URL",
    "NEXT_PUBLIC_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL",
    "NEXT_PUBLIC_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL",
    "NEXT_PUBLIC_PLATO_HOSTED_BILLING",
    "PLATO_PUBLICATIONS_DATABASE_URL",
    "DATABASE_URL",
    "PLATO_REDIS_URL",
    "PLATO_USE_FAKEREDIS",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "PERPLEXITY_API_KEY",
)

CLERK_APP_PATH_KEYS = (
    "NEXT_PUBLIC_CLERK_SIGN_IN_URL",
    "NEXT_PUBLIC_CLERK_SIGN_UP_URL",
    "NEXT_PUBLIC_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL",
    "NEXT_PUBLIC_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL",
)

LLM_PROVIDER_KEYS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "PERPLEXITY_API_KEY",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate hosted Plato SaaS/Lab deployment variables.",
    )
    parser.add_argument(
        "--source",
        choices=("env", "railway"),
        default="env",
        help="Read variables from the process env or Railway JSON on stdin.",
    )
    parser.add_argument(
        "--hosted-required",
        action="store_true",
        help="Require hosted Clerk mode even when provider flags are absent.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when warnings are emitted, not only errors.",
    )
    return parser.parse_args()


def read_values(source: str) -> dict[str, str]:
    if source == "env":
        return dict(os.environ)

    raw = sys.stdin.read()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"preflight: failed to parse Railway variables JSON: {exc}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(parsed, dict):
        print("preflight: expected Railway variables JSON object", file=sys.stderr)
        sys.exit(2)
    return {str(key): "" if value is None else str(value) for key, value in parsed.items()}


def value(values: dict[str, str], name: str) -> str:
    return values.get(name, "").strip()


def safe_status(values: dict[str, str], name: str) -> str:
    return "set" if value(values, name) else "missing"


def parse_https_origin(raw: str):
    if not raw:
        return None
    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path not in ("", "/"):
        return None
    return parsed


def parse_https_url(raw: str):
    if not raw:
        return None
    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.netloc:
        return None
    return parsed


def app_path_valid(raw: str) -> bool:
    if not raw:
        return True
    parsed = urlparse(raw)
    return (
        raw.startswith("/")
        and not raw.startswith("//")
        and parsed.scheme == ""
        and parsed.netloc == ""
    )


def publishable_key_valid(values: dict[str, str]) -> bool:
    raw = value(values, "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY")
    if not re.fullmatch(r"pk_(test|live)_[A-Za-z0-9_-]+", raw):
        return False

    encoded = raw.split("_", 2)[2]
    padded = encoded + ("=" * (-len(encoded) % 4))
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("ascii")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False
    return decoded.endswith("$") and "$" not in decoded[:-1] and "." in decoded[:-1]


def secret_key_valid(values: dict[str, str]) -> bool:
    raw = value(values, "CLERK_SECRET_KEY")
    return bool(re.fullmatch(r"sk_(test|live)_[A-Za-z0-9_-]+", raw))


def backend_proxy_secret_available(values: dict[str, str]) -> bool:
    return len(value(values, "PLATO_BACKEND_PROXY_SECRET")) >= 32 or secret_key_valid(values)


def main() -> int:
    args = parse_args()
    values = read_values(args.source)

    provider_values = {
        "NEXT_PUBLIC_PLATO_AUTH_PROVIDER": value(values, "NEXT_PUBLIC_PLATO_AUTH_PROVIDER"),
        "PLATO_AUTH_PROVIDER": value(values, "PLATO_AUTH_PROVIDER"),
    }
    hosted_requested = args.hosted_required or any(
        item == "clerk" for item in provider_values.values()
    )

    errors: list[str] = []
    warnings: list[str] = []

    if not hosted_requested:
        print("Hosted SaaS/Lab preflight: skipped")
        print("  Clerk provider flags are not set. Pass --hosted-required to require hosted mode.")
        return 0

    for name in ("NEXT_PUBLIC_PLATO_AUTH_PROVIDER", "PLATO_AUTH_PROVIDER"):
        if value(values, name) != "clerk":
            errors.append(f"{name} must be set to 'clerk' for hosted SaaS/Lab mode")

    if not publishable_key_valid(values):
        errors.append(
            "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY is missing or does not look like a Clerk publishable key",
        )

    if not secret_key_valid(values):
        errors.append("CLERK_SECRET_KEY is missing or does not look like a Clerk secret key")

    if not backend_proxy_secret_available(values):
        errors.append(
            "PLATO_BACKEND_PROXY_SECRET must be set to at least 32 characters, "
            "or CLERK_SECRET_KEY must be present so the backend proxy secret can be derived",
        )

    public_origin = value(values, "PLATO_PUBLIC_ORIGIN")
    clerk_proxy_url = value(values, "NEXT_PUBLIC_CLERK_PROXY_URL")

    parsed_public_origin = parse_https_origin(public_origin)
    if not public_origin:
        warnings.append(
            "PLATO_PUBLIC_ORIGIN should be the canonical HTTPS app origin, e.g. https://discovering.app",
        )
    elif parsed_public_origin is None:
        errors.append("PLATO_PUBLIC_ORIGIN must be an HTTPS origin without a path")

    parsed_clerk_proxy_url = parse_https_url(clerk_proxy_url)
    if not clerk_proxy_url:
        warnings.append("NEXT_PUBLIC_CLERK_PROXY_URL is not set; default /__clerk proxy is used")
    elif parsed_clerk_proxy_url is None:
        errors.append("NEXT_PUBLIC_CLERK_PROXY_URL must be an HTTPS URL")
    elif parsed_clerk_proxy_url.path.rstrip("/") != "/__clerk":
        errors.append("NEXT_PUBLIC_CLERK_PROXY_URL must point to the /__clerk proxy path")
    elif parsed_public_origin is not None and (
        parsed_clerk_proxy_url.scheme,
        parsed_clerk_proxy_url.netloc,
    ) != (parsed_public_origin.scheme, parsed_public_origin.netloc):
        errors.append("NEXT_PUBLIC_CLERK_PROXY_URL must use the PLATO_PUBLIC_ORIGIN host")

    for name in CLERK_APP_PATH_KEYS:
        if not app_path_valid(value(values, name)):
            errors.append(f"{name} must be a same-origin app path starting with '/'")

    if value(values, "NEXT_PUBLIC_PLATO_HOSTED_BILLING") != "enabled":
        warnings.append(
            "NEXT_PUBLIC_PLATO_HOSTED_BILLING is not enabled; Clerk Billing UI stays disabled",
        )

    publication_db_configured = bool(
        value(values, "PLATO_PUBLICATIONS_DATABASE_URL") or value(values, "DATABASE_URL")
    )
    if not publication_db_configured:
        errors.append(
            "PLATO_PUBLICATIONS_DATABASE_URL or DATABASE_URL must be set for durable hosted publications",
        )

    if not value(values, "PLATO_REDIS_URL"):
        warnings.append(
            "PLATO_REDIS_URL is not set; hosted runs use the single-container Redis fallback",
        )

    use_fakeredis = value(values, "PLATO_USE_FAKEREDIS").lower()
    if use_fakeredis not in {"false", "disabled", "0"}:
        warnings.append("PLATO_USE_FAKEREDIS should be false when PLATO_REDIS_URL is set")

    if not any(value(values, name) for name in LLM_PROVIDER_KEYS):
        errors.append(
            "At least one LLM provider key must be set for hosted user/Lab workflows",
        )

    print("Hosted SaaS/Lab preflight:")
    for name in CHECKED_KEYS:
        raw = value(values, name)
        suffix = f" ({len(raw)} chars)" if raw else ""
        print(f"  {name}: {safe_status(values, name)}{suffix}")

    if warnings:
        print("\nWarnings:")
        for item in warnings:
            print(f"  - {item}")

    strict_failures: list[str] = []
    if args.strict and warnings:
        strict_failures.append("hosted preflight emitted warnings")

    if errors or strict_failures:
        print("\nErrors:")
        for item in errors:
            print(f"  - {item}")
        for item in strict_failures:
            print(f"  - {item}")
        return 1

    print("\nOK: hosted SaaS/Lab required variables are present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
