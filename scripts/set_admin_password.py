#!/usr/bin/env python3
"""Set or reset the built-in admin password.

Usage (inside the container or on the host with the same workspace):

    python3 scripts/set_admin_password.py                 # prompt
    SOFTWIKI_ADMIN_PASSWORD=... python3 scripts/set_admin_password.py --from-env

The account is always role ``wiki-admin`` and always named ``admin``. It is an
escape hatch for installations without an identity provider, not a user system.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from softwiki.identity.localauth import set_builtin_admin_password  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from-env", action="store_true",
                    help="read the password from SOFTWIKI_ADMIN_PASSWORD")
    args = ap.parse_args()

    if args.from_env:
        password = os.getenv("SOFTWIKI_ADMIN_PASSWORD", "")
        if not password:
            print("SOFTWIKI_ADMIN_PASSWORD is empty", file=sys.stderr)
            return 2
    else:
        password = getpass.getpass("New admin password: ")
        confirm = getpass.getpass("Repeat: ")
        if password != confirm:
            print("passwords do not match", file=sys.stderr)
            return 2

    try:
        admin = set_builtin_admin_password(password)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"updated {admin.identity} (role {admin.role_override})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
