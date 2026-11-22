"""NotifyHub 管理命令。"""

import argparse
import getpass
import os
import sys

from app.core.logging import setup_logging
from app.database import SessionLocal
from app.schemas.user import UserRegister
from app.services import user_service


def _read_it_support_inputs(args: argparse.Namespace) -> tuple[str, str, str | None]:
    email = args.email or os.getenv("IT_SUPPORT_EMAIL", "")
    username = args.username or os.getenv("IT_SUPPORT_USERNAME", "")
    password = args.password or os.getenv("IT_SUPPORT_PASSWORD", "")

    if not email:
        email = input("IT support email: ").strip()
    if not username:
        username = input("IT support username: ").strip()
    if not password and sys.stdin.isatty():
        password = getpass.getpass("IT support password: ")

    # 使用与注册接口相同的字段校验，避免 CLI 写入非法账号。
    validated = UserRegister(
        username=username,
        email=email,
        password=password or "Placeholder123!",
    )
    return str(validated.email), validated.username, password or None


def create_it_support(args: argparse.Namespace) -> int:
    email, username, password = _read_it_support_inputs(args)
    with SessionLocal() as db:
        user, created = user_service.create_it_support_user(
            db,
            email=email,
            username=username,
            password=password,
        )
        action = "created" if created else "promoted"
        print(f"IT support account {action}: {user.email} (role={user.role})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NotifyHub 管理命令")
    subparsers = parser.add_subparsers(dest="command", required=True)

    support = subparsers.add_parser(
        "create-it-support",
        help="创建或提升 IT 支持账号（幂等）",
    )
    support.add_argument("--email", default="")
    support.add_argument("--username", default="")
    support.add_argument("--password", default="")
    support.set_defaults(handler=create_it_support)
    return parser


def main() -> int:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
