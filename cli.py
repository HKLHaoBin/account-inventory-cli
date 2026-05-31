"""Interactive CLI for account inbound/outbound management."""

from __future__ import annotations

import database as db
from batch import (
    InboundFailure,
    InboundPending,
    InboundReady,
    classify_inbound_line,
)
from parser import format_account


def render_home(inventory: int) -> None:
    print()
    print("========== 账号出入库管理 ==========")
    print(f"当前库存：{inventory}")
    print()
    print("[0] 录入账号（支持多行批量，空行结束）")
    print("    格式：账号----密码----邮箱----邮箱密码")
    print("    前两段必填，后两段可选")
    print()
    print("[1] 出库账号（可指定数量，FIFO，自动复制到剪贴板）")
    print()
    print("[q] 退出")
    print()
    print("请输入操作：", end="", flush=True)


def copy_to_clipboard(text: str) -> bool:
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
        return True
    except Exception:
        return False


def _read_inbound_lines() -> list[str]:
    print()
    print("请输入账号信息（每行一条，输入空行结束）：")
    lines: list[str] = []
    while True:
        line = input().strip()
        if not line:
            break
        lines.append(line)
    return lines


def _parse_indices(raw: str, max_index: int) -> list[int]:
    indices: list[int] = []
    for part in raw.replace(",", " ").split():
        if not part.isdigit():
            continue
        idx = int(part)
        if 1 <= idx <= max_index and idx not in indices:
            indices.append(idx)
    return indices


def _print_pending_list(pending: list[InboundPending]) -> None:
    print()
    print(f"以下 {len(pending)} 个账号曾出现在出库记录中，需确认是否入库：")
    for i, item in enumerate(pending, start=1):
        latest = db.get_latest_outbound_time(item.username)
        time_hint = f"（最近出库：{latest}）" if latest else ""
        print(f"  [{i}] {item.username}  {time_hint}")
    print()
    print("命令：")
    print("  a <序号>     批准选中条目入库（如 a 1,3 或 a 1 3）")
    print("  c <序号>     取消选中条目（如 c 2）")
    print("  a all        批准全部待确认条目")
    print("  done         结束确认（未处理条目视为取消）")
    print("  list         重新显示列表")
    print()


def _review_pending(pending: list[InboundPending]) -> tuple[int, list[InboundFailure]]:
    success_count = 0
    failures: list[InboundFailure] = []

    while pending:
        _print_pending_list(pending)
        print("确认 > ", end="", flush=True)
        command = input().strip()
        if not command:
            continue

        parts = command.split(maxsplit=1)
        action = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if action == "list":
            continue

        if action == "done":
            for item in pending:
                failures.append(
                    InboundFailure(
                        line=item.line,
                        reason="用户取消录入（曾出现在出库记录）",
                    )
                )
            pending.clear()
            break

        if action == "a" and args.lower() == "all":
            for item in list(pending):
                db.insert_account(
                    item.username,
                    item.password,
                    item.email,
                    item.email_password,
                )
                success_count += 1
            pending.clear()
            break

        if action == "a":
            indices = _parse_indices(args, len(pending))
            if not indices:
                print("未识别有效序号，请重试。")
                continue
            for idx in sorted(indices, reverse=True):
                item = pending[idx - 1]
                db.insert_account(
                    item.username,
                    item.password,
                    item.email,
                    item.email_password,
                )
                success_count += 1
                pending.pop(idx - 1)
            continue

        if action == "c":
            indices = _parse_indices(args, len(pending))
            if not indices:
                print("未识别有效序号，请重试。")
                continue
            for idx in sorted(indices, reverse=True):
                item = pending[idx - 1]
                failures.append(
                    InboundFailure(
                        line=item.line,
                        reason="用户取消录入（曾出现在出库记录）",
                    )
                )
                pending.pop(idx - 1)
            continue

        print("无效命令，请输入 a / c / a all / done / list")

    return success_count, failures


def _print_inbound_summary(success_count: int, failures: list[InboundFailure]) -> None:
    print()
    print(f"批量录入完成：成功 {success_count} 条，失败 {len(failures)} 条")
    print(f"当前库存：{db.count_inventory()}")
    if failures:
        print()
        print("失败明细：")
        for i, failure in enumerate(failures, start=1):
            print(f"  {i}. [{failure.reason}]")
            print(f"     {failure.line}")


def handle_inbound() -> None:
    lines = _read_inbound_lines()
    if not lines:
        return

    seen_usernames: set[str] = set()
    pending: list[InboundPending] = []
    failures: list[InboundFailure] = []
    success_count = 0

    for line in lines:
        result = classify_inbound_line(
            line,
            seen_usernames,
            exists_in_inventory=db.exists_in_inventory,
            exists_in_outbound=db.exists_in_outbound,
        )
        if isinstance(result, InboundFailure):
            failures.append(result)
        elif isinstance(result, InboundPending):
            pending.append(result)
        elif isinstance(result, InboundReady):
            db.insert_account(
                result.username,
                result.password,
                result.email,
                result.email_password,
            )
            seen_usernames.add(result.username)
            success_count += 1

    if pending:
        approved, cancelled = _review_pending(pending)
        success_count += approved
        failures.extend(cancelled)

    _print_inbound_summary(success_count, failures)


def handle_outbound() -> None:
    inventory = db.count_inventory()
    if inventory == 0:
        print("当前无库存，无法出库")
        return

    print()
    print("请输入出库数量（直接回车默认为 1）：", end="", flush=True)
    raw = input().strip()
    if not raw:
        count = 1
    else:
        if not raw.isdigit() or int(raw) <= 0:
            print("无效数量，请输入正整数")
            return
        count = int(raw)

    count = min(count, inventory)
    records = db.outbound_oldest_many(count)
    if not records:
        print("当前无库存，无法出库")
        return

    lines = [
        format_account(
            record["username"],
            record["password"],
            record["email"],
            record["email_password"],
        )
        for record in records
    ]
    text = "\n".join(lines)

    print()
    print("出库成功：")
    for line in lines:
        print(line)

    if copy_to_clipboard(text):
        print("已复制到剪贴板")
    else:
        print("复制失败，请手动复制")
    print(f"当前库存：{db.count_inventory()}")


def main_loop() -> None:
    try:
        while True:
            render_home(db.count_inventory())
            command = input().strip().lower()
            if command == "0":
                handle_inbound()
            elif command == "1":
                handle_outbound()
            elif command == "q":
                print("再见。")
                break
            else:
                print("无效命令，请输入 0、1 或 q")
    except KeyboardInterrupt:
        print()
        print("再见。")
