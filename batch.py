"""Pure logic for batch inbound classification (no I/O)."""

from __future__ import annotations

from collections.abc import Sequence
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
    url: str | None = None


@dataclass(frozen=True)
class InboundPending:
    line: str
    username: str
    password: str
    email: str | None = None
    email_password: str | None = None
    url: str | None = None


def classify_inbound_line(
    line: str,
    seen_usernames: set[str],
    *,
    exists_in_inventory: Callable[[str], bool],
    exists_in_outbound: Callable[[str], bool],
    separators: Sequence[str] | None = None,
) -> InboundReady | InboundPending | InboundFailure:
    try:
        username, password, email, email_password, url = parse_account_line(
            line, separators
        )
    except ValueError as exc:
        return InboundFailure(line=line, reason=str(exc))

    if exists_in_inventory(username):
        return InboundFailure(line=line, reason=f"账号 {username} 已在组内库存中")

    if username in seen_usernames:
        return InboundFailure(line=line, reason="本批次内账号重复")

    if exists_in_outbound(username):
        return InboundPending(
            line=line,
            username=username,
            password=password,
            email=email,
            email_password=email_password,
            url=url,
        )

    return InboundReady(
        line=line,
        username=username,
        password=password,
        email=email,
        email_password=email_password,
        url=url,
    )


@dataclass(frozen=True)
class OutboundFailure:
    line: str
    reason: str


@dataclass(frozen=True)
class OutboundReady:
    line: str
    username: str
    password: str
    email: str | None = None
    email_password: str | None = None
    url: str | None = None


def classify_outbound_line(
    line: str,
    seen_usernames: set[str],
    *,
    exists_in_inventory: Callable[[str], bool],
    exists_in_outbound: Callable[[str], bool],
    separators: Sequence[str] | None = None,
) -> OutboundReady | OutboundFailure:
    try:
        username, password, email, email_password, url = parse_account_line(
            line, separators
        )
    except ValueError as exc:
        return OutboundFailure(line=line, reason=str(exc))

    if username in seen_usernames:
        return OutboundFailure(line=line, reason="本批次内账号重复")

    if exists_in_outbound(username) and not exists_in_inventory(username):
        return OutboundFailure(line=line, reason="已在出库记录中")

    return OutboundReady(
        line=line,
        username=username,
        password=password,
        email=email,
        email_password=email_password,
        url=url,
    )
