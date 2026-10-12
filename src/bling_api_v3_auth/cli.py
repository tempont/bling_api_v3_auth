"""Command line interface: ``bling-auth``."""

from __future__ import annotations

import argparse
import importlib.util
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from bling_api_v3_auth._version import __version__
from bling_api_v3_auth.exceptions import BlingApiError, BlingOAuthError
from bling_api_v3_auth.manager import BlingAuthManager


def _default_env_file() -> str | None:
    if Path(".env").is_file() and importlib.util.find_spec("dotenv") is not None:
        return ".env"
    return None


def parse_callback(value: str) -> tuple[str, str | None]:
    """Extract ``(code, state)`` from a pasted redirect URL, query string or bare code.

    Raises:
        BlingOAuthError: If the redirect carries an ``error`` (e.g. ``access_denied``).
    """
    value = value.strip()
    if "code=" not in value and "error=" not in value:
        return value, None
    query = urlsplit(value).query if "://" in value else value.lstrip("?")
    params = parse_qs(query)
    if "error" in params:
        error = params["error"][0]
        description = params.get("error_description", [""])[0]
        msg = f"Authorization failed - {error}: {description}"
        raise BlingOAuthError(msg, error=error, description=description)
    code = params.get("code", [""])[0]
    state = params.get("state", [None])[0]
    return code, state


def _format_ts(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(ts))


def _cmd_url(manager: BlingAuthManager, args: argparse.Namespace) -> int:
    url, state = manager.authorization_url(args.state)
    print(url)
    print(f"state: {state}", file=sys.stderr)
    return 0


def _cmd_login(manager: BlingAuthManager, _args: argparse.Namespace) -> int:
    url, state = manager.authorization_url()
    print("1. Open this URL, log in to Bling and authorize the application:\n")
    print(f"   {url}\n")
    print("2. Paste the URL you were redirected to (or just the `code` parameter).")
    print("   The code expires in about 1 minute.\n")
    code, received_state = parse_callback(input("> "))
    if received_state is not None and received_state != state:
        print("error: state mismatch - possible CSRF, aborting.", file=sys.stderr)
        return 1
    if not code:
        print("error: no code provided.", file=sys.stderr)
        return 1
    token = manager.authorize(code)
    print(f"\nAuthorized. Access token valid until {_format_ts(token.expires_at)}.")
    return 0


def _cmd_authorize(manager: BlingAuthManager, args: argparse.Namespace) -> int:
    code, _ = parse_callback(args.code)
    token = manager.authorize(code)
    print(f"Authorized. Access token valid until {_format_ts(token.expires_at)}.")
    return 0


def _cmd_token(manager: BlingAuthManager, args: argparse.Namespace) -> int:
    print(manager.get_access_token(force_refresh=args.refresh))
    return 0


def _cmd_status(manager: BlingAuthManager, _args: argparse.Namespace) -> int:
    token = manager.storage.load()
    if token is None:
        print("No tokens stored. Run: bling-auth login")
        return 1
    access = "expired" if token.is_access_token_expired() else "valid"
    refresh = "expired" if token.is_refresh_token_expired() else "valid"
    print(f"storage:        {type(manager.storage).__name__}")
    print(f"access token:   {access} (until {_format_ts(token.expires_at)})")
    print(
        f"refresh token:  {refresh} (estimated until {_format_ts(token.refresh_token_expires_at)})"
    )
    if token.scope:
        print(f"scope:          {token.scope}")
    return 0


def _cmd_revoke(manager: BlingAuthManager, _args: argparse.Namespace) -> int:
    manager.revoke()
    print("Tokens revoked and removed from storage.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the ``bling-auth`` argument parser."""
    parser = argparse.ArgumentParser(
        prog="bling-auth",
        description="Manage OAuth 2.0 tokens for the Bling ERP API v3.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--env-file",
        default=None,
        help="Path to a .env file (default: ./.env when present and python-dotenv is installed)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("login", help="interactive authorization (prints URL, asks for the code)")

    p_url = sub.add_parser("url", help="print the authorization URL")
    p_url.add_argument("--state", help="state value to use (random by default)")

    p_auth = sub.add_parser("authorize", help="exchange an authorization code for tokens")
    p_auth.add_argument("code", help="the `code` parameter, or the full redirect URL")

    p_token = sub.add_parser("token", help="print a valid access token (refreshing if needed)")
    p_token.add_argument("--refresh", action="store_true", help="force a refresh")

    sub.add_parser("status", help="show token expiration info (never prints tokens)")
    sub.add_parser("revoke", help="revoke the stored tokens and delete them")
    return parser


_COMMANDS = {
    "login": _cmd_login,
    "url": _cmd_url,
    "authorize": _cmd_authorize,
    "token": _cmd_token,
    "status": _cmd_status,
    "revoke": _cmd_revoke,
}


def main(argv: list[str] | None = None) -> int:
    """Entry point of the ``bling-auth`` command."""
    args = build_parser().parse_args(argv)
    env_file = args.env_file if args.env_file is not None else _default_env_file()
    try:
        manager = BlingAuthManager.from_env(env_file=env_file)
        return _COMMANDS[args.command](manager, args)
    except BlingApiError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:  # pragma: no cover - interactive
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
