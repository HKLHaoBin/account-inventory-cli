"""Pure logic for batch inbound classification (no I/O)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from parser import parse_account_line


@dataclass(frozen=True)
class InboundFailure:
    line: str
    reason: str


@dataclass
class InboundResult:
    success_count: int
    failures: list[InboundFailure]


@dataclass(frozen=True)
class InboundReady:
    line: str
    username: str
    password: str
    email: str | None = None
    email_password: str | None = None


@dataclass(frozen=True)
class InboundPending:
    line: str
    username: str
    password: str
    email: str | None = None
    email_password: str | None = None


def classify_inbound_line(
    line: str,
    seen_usernames: set[str],
    *,
    exists_in_inventory: Callable[[str], bool],
    exists_in_outbound: Callable[[str], bool],
) -> InboundReady | InboundPending | InboundFailure:
    try:
        username, password, email, email_password = parse_account_line(line)
    except ValueError as exc:
        return InboundFailure(line=line, reason=str(exc))

    if exists_in_inventory(username):
        return InboundFailure(line=line, reason=f"账号 {username} 已在库存中")

    if username in seen_usernames:
        return InboundFailure(line=line, reason="本批次内账号重复")

    if exists_in_outbound(username):
        return InboundPending(
            line=line,
            username=username,
            password=password,
            email=email,
            email_password=email_password,
        )

    return InboundReady(
        line=line,
        username=username,
        password=password,
        email=email,
        email_password=email_password,
    )
