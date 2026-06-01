"""Parse and format account lines using ---- separators."""

from __future__ import annotations


def parse_account_line(line: str) -> tuple[str, str, str | None, str | None, str | None]:
    """Parse account----password----email----email_password----url (2-5 fields)."""
    stripped = line.strip()
    if not stripped:
        raise ValueError("输入不能为空")

    parts = [p.strip() for p in stripped.split("----")]
    if len(parts) < 2:
        raise ValueError("格式错误：至少需要「账号----密码」两段")
    if len(parts) > 5:
        raise ValueError(
            "格式错误：最多 5 段（账号----密码----邮箱----邮箱密码----网址）"
        )

    username, password = parts[0], parts[1]
    if not username:
        raise ValueError("账号不能为空")
    if not password:
        raise ValueError("密码不能为空")

    email: str | None = None
    email_password: str | None = None
    url: str | None = None
    if len(parts) == 4 and not parts[2]:
        email = None
        email_password = None
        url = parts[3] or None
    else:
        if len(parts) >= 3:
            email = parts[2] or None
        if len(parts) >= 4:
            email_password = parts[3] or None
        if len(parts) >= 5:
            url = parts[4] or None

    return username, password, email, email_password, url


def extract_valid_account_lines(text: str) -> tuple[list[str], int]:
    """Return (valid_lines, rejected_count). One entry per kept line."""
    valid: list[str] = []
    rejected = 0
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            rejected += 1
            continue
        try:
            parse_account_line(stripped)
        except ValueError:
            rejected += 1
            continue
        valid.append(stripped)
    return valid, rejected


def format_account(
    username: str,
    password: str,
    email: str | None = None,
    email_password: str | None = None,
    url: str | None = None,
) -> str:
    """Format for display and clipboard."""
    if email is None and email_password is None and url is None:
        return f"{username}----{password}"
    if url is not None and email is None and email_password is None:
        return f"{username}----{password}--------{url}"
    if url is None:
        return "----".join(
            [username, password, email or "", email_password or ""]
        )
    return "----".join(
        [username, password, email or "", email_password or "", url or ""]
    )
