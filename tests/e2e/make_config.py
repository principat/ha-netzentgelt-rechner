"""Write a throwaway Home Assistant config dir (onboarding done, long-lived token).

Usage: python make_config.py <config_dir>
The access token is written to ``<config_dir>/.e2e_token`` (synthetic, never committed).
"""

from __future__ import annotations

import json
import secrets
import sys
import time
import uuid
from pathlib import Path

import jwt  # PyJWT, a dependency of Home Assistant

CONFIGURATION = """\
homeassistant:
  name: E2E
  time_zone: Europe/Berlin
  unit_system: metric
  country: DE
  currency: EUR
http:
logger:
  default: warning
  logs:
    custom_components.netzentgelt_rechner: debug
recorder:
  commit_interval: 1
default_config:
"""


def main(config_dir: Path) -> None:
    storage = config_dir / ".storage"
    storage.mkdir(parents=True, exist_ok=True)
    (config_dir / "configuration.yaml").write_text(CONFIGURATION, encoding="utf-8")

    user_id = uuid.uuid4().hex
    token_id = uuid.uuid4().hex
    jwt_key = secrets.token_hex(64)
    now = int(time.time())
    auth = {
        "version": 1,
        "minor_version": 1,
        "key": "auth",
        "data": {
            "users": [
                {
                    "id": user_id,
                    "group_ids": ["system-admin"],
                    "is_owner": True,
                    "is_active": True,
                    "name": "e2e",
                    "system_generated": False,
                    "local_only": False,
                }
            ],
            "groups": [
                {"id": "system-admin", "name": "Administrators"},
                {"id": "system-users", "name": "Users"},
                {"id": "system-read-only", "name": "Read Only"},
            ],
            "credentials": [],
            "refresh_tokens": [
                {
                    "id": token_id,
                    "user_id": user_id,
                    "client_id": None,
                    "client_name": "e2e",
                    "client_icon": None,
                    "token_type": "long_lived_access_token",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "access_token_expiration": 315360000.0,
                    "token": secrets.token_hex(64),
                    "jwt_key": jwt_key,
                    "last_used_at": None,
                    "last_used_ip": None,
                    "expire_at": None,
                    "credential_id": None,
                    "version": "2026.2.0",
                }
            ],
        },
    }
    (storage / "auth").write_text(json.dumps(auth), encoding="utf-8")
    onboarding = {
        "version": 4,
        "minor_version": 1,
        "key": "onboarding",
        "data": {"done": ["user", "core_config", "analytics", "integration"]},
    }
    (storage / "onboarding").write_text(json.dumps(onboarding), encoding="utf-8")
    access = jwt.encode(
        {"iss": token_id, "iat": now, "exp": now + 315360000}, jwt_key, algorithm="HS256"
    )
    (config_dir / ".e2e_token").write_text(access, encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
