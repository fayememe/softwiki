"""Move knowledge bases into per-stack roots.

Why: every compose stack used to mount the *shared* workspace parent, so a
stack could read every other stack's documents, exports and indexes. Only the
databases were separated. The fix is a stack-private root:

    workspace/
    ├── stacks/
    │   ├── coffee/
    │   │   └── coffee/            <- knowledge base
    │   └── ai/
    │       └── ai-history/
    ├── config/                    <- shared (identity)
    └── .softwiki-audit/           <- shared (audit log)

A stack mounts `workspace/stacks/<stack>` as `/data/workspaces`, so it can only
see the kbs placed there. Adding a kb to a stack = put another directory in its
root (plus a PostgreSQL database).

Usage:
    python3 scripts/kb_layout_migrate.py --stack coffee --kb coffee
    python3 scripts/kb_layout_migrate.py --stack coffee --kb coffee --apply

Dry run by default: prints the plan and the env lines to set.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys


def plan(root: str, stack: str, kb: str) -> dict:
    source = os.path.join(root, kb)
    target_root = os.path.join(root, "stacks", stack)
    target = os.path.join(target_root, kb)
    return {
        "source": source,
        "target": target,
        "target_root": target_root,
        "source_exists": os.path.isdir(source),
        "target_exists": os.path.isdir(target),
        "is_kb": os.path.isdir(os.path.join(source, ".softwiki")),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", default=os.getenv("SOFTWIKI_WORKSPACE", "workspace"),
                    help="workspace parent directory (default: ./workspace)")
    ap.add_argument("--stack", required=True, help="stack name, e.g. coffee")
    ap.add_argument("--kb", required=True, help="knowledge base directory name")
    ap.add_argument("--apply", action="store_true", help="actually move (default: dry run)")
    args = ap.parse_args()

    root = os.path.abspath(args.workspace)
    p = plan(root, args.stack, args.kb)

    if p["target_exists"]:
        print(f"already migrated: {p['target']}")
        _print_env(args.stack, args.kb)
        return 0

    if not p["source_exists"]:
        print(f"error: {p['source']} does not exist", file=sys.stderr)
        return 2

    if not p["is_kb"]:
        print(
            f"error: {p['source']} is not an initialised kb (no .softwiki/); "
            "refusing to move it",
            file=sys.stderr,
        )
        return 2

    print(f"move: {p['source']}\n   -> {p['target']}")
    _print_env(args.stack, args.kb)

    if not args.apply:
        print("\n(dry run — pass --apply to perform the move)")
        return 0

    os.makedirs(p["target_root"], exist_ok=True)
    shutil.move(p["source"], p["target"])
    print(f"\nmoved. stack root: {p['target_root']}")
    return 0


def _print_env(stack: str, kb: str) -> None:
    print("\nenv for this stack:")
    print(f"  SOFTWIKI_STACK_ROOT=./workspace/stacks/{stack}")
    print(f"  SOFTWIKI_ACTIVE_WORKSPACE={kb}")
    print(f"  WIKIWEB_DIR=./workspace/stacks/{stack}/{kb}/exports/wikiweb")
    print(f"  WIKIWEB_ENTRY={kb}/index.html")


if __name__ == "__main__":
    raise SystemExit(main())
