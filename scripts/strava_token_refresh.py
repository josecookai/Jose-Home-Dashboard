"""
strava_token_refresh.py — Standalone Strava access-token refresh utility.

Use this script to manually refresh the Strava access token before it expires,
or to bootstrap a new token after initial OAuth authorisation.

Env vars required (loaded from ../.env relative to this script):
    STRAVA_REFRESH_TOKEN
    STRAVA_CLIENT_ID
    STRAVA_CLIENT_SECRET

After a successful refresh the script writes the new STRAVA_ACCESS_TOKEN (and
optionally a rotated STRAVA_REFRESH_TOKEN) back to the .env file.
"""

from __future__ import annotations

import os
import sys
import datetime
import logging
from pathlib import Path

import requests
from dotenv import load_dotenv, set_key

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
ENV_FILE = PROJECT_ROOT / ".env"

load_dotenv(ENV_FILE)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("strava_token_refresh")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_env(key: str) -> str:
    """Return the value of *key* from the environment, raising clearly if absent."""
    value = os.environ.get(key, "")
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            f"Add it to {ENV_FILE} or export it before running this script."
        )
    return value


def refresh_access_token() -> dict[str, str]:
    """
    Exchange the current refresh token for a new access token.

    Returns a dict with at minimum:
        access_token  — the new access token
        refresh_token — the (possibly rotated) refresh token
        expires_at    — Unix timestamp when the new access token expires
    """
    client_id = _require_env("STRAVA_CLIENT_ID")
    client_secret = _require_env("STRAVA_CLIENT_SECRET")
    refresh_token = _require_env("STRAVA_REFRESH_TOKEN")

    log.info("Requesting new access token from Strava…")

    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    response = requests.post(STRAVA_TOKEN_URL, data=payload, timeout=15)

    if not response.ok:
        raise RuntimeError(
            f"Token refresh request failed [{response.status_code}]: {response.text}"
        )

    token_data: dict = response.json()

    # Validate that the expected fields are present.
    for field in ("access_token", "expires_at"):
        if field not in token_data:
            raise ValueError(
                f"Strava token response missing expected field '{field}': {token_data}"
            )

    return token_data


def persist_tokens(token_data: dict) -> None:
    """
    Write the refreshed tokens back to .env so subsequent runs use them.
    Also updates the in-process environment.
    """
    new_access_token: str = token_data["access_token"]
    # Strava may rotate the refresh token; fall back to the current one if not.
    new_refresh_token: str = token_data.get(
        "refresh_token", os.environ.get("STRAVA_REFRESH_TOKEN", "")
    )

    env_path = str(ENV_FILE)
    set_key(env_path, "STRAVA_ACCESS_TOKEN", new_access_token)
    set_key(env_path, "STRAVA_REFRESH_TOKEN", new_refresh_token)

    # Reflect changes into the current process as well.
    os.environ["STRAVA_ACCESS_TOKEN"] = new_access_token
    os.environ["STRAVA_REFRESH_TOKEN"] = new_refresh_token

    expires_at: int = token_data["expires_at"]
    human_expiry = datetime.datetime.utcfromtimestamp(expires_at).isoformat() + "Z"

    log.info("Tokens written to %s", env_path)
    log.info("New access token expires at %s", human_expiry)

    # Warn if the token rotated so the caller knows the .env changed.
    stored_refresh = os.environ.get("STRAVA_REFRESH_TOKEN", "")
    if new_refresh_token and new_refresh_token != stored_refresh:
        log.info("Refresh token was rotated and has been updated in .env")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("=== Strava token refresh started ===")

    try:
        token_data = refresh_access_token()
        persist_tokens(token_data)
        log.info("=== Token refresh complete ===")

    except EnvironmentError as exc:
        log.error("Configuration error: %s", exc)
        sys.exit(1)

    except requests.RequestException as exc:
        log.error("Network error while contacting Strava: %s", exc)
        sys.exit(1)

    except (RuntimeError, ValueError) as exc:
        log.error("Token refresh failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
