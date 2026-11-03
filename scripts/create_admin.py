import argparse
from getpass import getpass

from softwiki.auth import hash_password
from softwiki.auth_db import get_auth_session
from softwiki.source_store.models import User, WorkspaceMember


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="admin")
    parser.add_argument("--role", default="admin")
    parser.add_argument("--workspace", default="kb-alpha")
    parser.add_argument("--password")
    args = parser.parse_args()

    password = args.password or getpass("Password: ")
    db = get_auth_session()
    try:
        user = db.query(User).filter(User.username == args.username).first()
        if user:
            user.password_hash = hash_password(password)
            user.role = args.role
            user.active_workspace = args.workspace
        else:
            db.add(User(
                username=args.username,
                password_hash=hash_password(password),
                role=args.role,
                active_workspace=args.workspace,
            ))
        member = db.query(WorkspaceMember).filter_by(
            username=args.username, workspace=args.workspace
        ).first()
        if not member:
            db.add(WorkspaceMember(
                username=args.username, workspace=args.workspace, role="owner"
            ))
        db.commit()
        print(f"user {args.username} ready (role={args.role}, workspace={args.workspace})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
