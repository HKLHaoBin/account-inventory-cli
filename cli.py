"""Interactive CLI for account inbound/outbound management."""

from __future__ import annotations

import clipboard
import console_input
import database as db
from batch import (
    InboundFailure,
    InboundPending,
    InboundReady,
    OutboundFailure,
    OutboundReady,
    classify_inbound_line,
    classify_outbound_line,
)
from parser import format_account, parse_account_line


def render_home(inventory: int) -> None:
    print()
    print("========== 账号出入库管理 ==========")
    print(f"当前库存：{inventory}")
    print()
    print("[0] 录入账号（入库 / 出库粘贴录入，多行批量，空行结束）")
    print("    格式：账号----密码----邮箱----邮箱密码----网址")
    print("    前两段必填，后三段可选")
    print()
    print("[1] 出库账号（可指定数量，FIFO，自动复制到剪贴板）")
    print()
    print("[2] 查找账号（子串匹配，先查库存再查出库历史）")
    print()
    print("Esc / Ctrl+C 退出")
    print()


def copy_to_clipboard(text: str) -> bool:
    return clipboard.copy_text(text)


def failure_lines_for_clipboard(failures: list[InboundFailure | OutboundFailure]) -> str:
    return "\n".join(f.line for f in failures)


def _print_mode_header(title: str) -> None:
    print()
    print(f"========== {title} ==========")
    print(f"当前库存：{db.count_inventory()}")
    print("Esc 返回首页")


def _read_batch_lines_or_exit(prompt: str) -> list[str] | None:
    print()
    print(prompt)
    lines: list[str] = []
    while True:
        line = console_input.read_line_or_exit("")
        if line is None:
            return None
        if not line:
            return lines
        lines.append(line)


def _parse_indices(raw: str, max_index: int) -> list[int]:
    indices: list[int] = []
    for part in raw.replace(",", " ").split():
        if not part.isdigit():
            continue
        idx = int(part)
        if 1 <= idx <= max_index and idx not in indices:
            indices.append(idx)
    return indices


def _clamp_cursor(cursor: int, pending_len: int) -> int:
    if pending_len <= 0:
        return 0
    return max(0, min(cursor, pending_len - 1))


def _render_pending_interactive(
    pending: list[InboundPending],
    cursor: int,
    selected: set[int],
    outbound_times: dict[str, str],
    *,
    vt_enabled: bool,
    message: str = "",
) -> None:
    lines: list[str] = [
        "",
        f"以下 {len(pending)} 个账号曾出现在出库记录中，需确认是否入库：",
        "",
    ]
    for i, item in enumerate(pending):
        marker = ">" if i == cursor else " "
        check = "[x]" if i in selected else "[ ]"
        latest = outbound_times.get(item.username)
        time_hint = f"（最近出库：{latest}）" if latest else ""
        lines.append(f"  {marker} {check} {item.username}  {time_hint}")
    lines.extend(
        [
            "",
            "操作：↑↓ 移动  空格/回车 切换选中  Y 批准选中  N 取消选中  Esc 结束",
            "命令：按 : 进入命令模式（a/c/a all/done/list）",
        ]
    )
    if message:
        lines.append(message)
    lines.append("")

    output = "\n".join(lines)
    if vt_enabled:
        print("\033[H\033[J", end="")
    print(output, end="", flush=True)


def _approve_pending_items(
    pending: list[InboundPending],
    indices: list[int],
) -> int:
    count = 0
    for idx in sorted(indices, reverse=True):
        item = pending[idx]
        db.insert_account(
            item.username,
            item.password,
            item.email,
            item.email_password,
            item.url,
        )
        count += 1
        pending.pop(idx)
    return count


def _cancel_pending_items(
    pending: list[InboundPending],
    indices: list[int],
) -> list[InboundFailure]:
    cancelled: list[InboundFailure] = []
    for idx in sorted(indices, reverse=True):
        item = pending[idx]
        cancelled.append(
            InboundFailure(
                line=item.line,
                reason="用户取消录入（曾出现在出库记录）",
            )
        )
        pending.pop(idx)
    return cancelled


def _execute_pending_command(
    command: str,
    pending: list[InboundPending],
    selected: set[int],
    *,
    success_count: int,
    failures: list[InboundFailure],
) -> tuple[int, str, bool]:
    if not command:
        return success_count, "", False

    parts = command.split(maxsplit=1)
    action = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if action == "list":
        return success_count, "", False

    if action == "done":
        failures.extend(
            _cancel_pending_items(pending, list(range(len(pending))))
        )
        pending.clear()
        return success_count, "", True

    if action == "a" and args.lower() == "all":
        success_count += _approve_pending_items(
            pending, list(range(len(pending)))
        )
        pending.clear()
        return success_count, "", True

    if action == "a":
        indices = _parse_indices(args, len(pending))
        if not indices:
            return success_count, "未识别有效序号，请重试。", False
        success_count += _approve_pending_items(
            pending, [idx - 1 for idx in indices]
        )
        selected.clear()
        return success_count, "", False

    if action == "c":
        indices = _parse_indices(args, len(pending))
        if not indices:
            return success_count, "未识别有效序号，请重试。", False
        failures.extend(
            _cancel_pending_items(pending, [idx - 1 for idx in indices])
        )
        selected.clear()
        return success_count, "", False

    return success_count, "无效命令，请输入 a / c / a all / done / list", False


def _review_pending(pending: list[InboundPending]) -> tuple[int, list[InboundFailure]]:
    success_count = 0
    failures: list[InboundFailure] = []
    cursor = 0
    selected: set[int] = set()
    vt_enabled = console_input.enable_vt_mode()
    message = ""
    keyboard = console_input.keyboard_supported()

    while pending:
        outbound_times = db.get_latest_outbound_times([item.username for item in pending])
        _render_pending_interactive(
            pending,
            cursor,
            selected,
            outbound_times,
            vt_enabled=vt_enabled,
            message=message,
        )
        message = ""

        if not keyboard:
            print("命令 > ", end="", flush=True)
            command = input().strip()
            success_count, message, done = _execute_pending_command(
                command,
                pending,
                selected,
                success_count=success_count,
                failures=failures,
            )
            cursor = _clamp_cursor(cursor, len(pending))
            if done:
                break
            continue

        key = console_input.read_key()
        if key == "up":
            cursor = (cursor - 1) % len(pending)
        elif key == "down":
            cursor = (cursor + 1) % len(pending)
        elif key in ("space", "enter"):
            if cursor in selected:
                selected.discard(cursor)
            else:
                selected.add(cursor)
        elif key == "y":
            if not selected:
                message = "请先选中条目"
            else:
                success_count += _approve_pending_items(
                    pending, sorted(selected)
                )
                selected.clear()
                cursor = _clamp_cursor(cursor, len(pending))
        elif key == "n":
            if not selected:
                message = "请先选中条目"
            else:
                failures.extend(
                    _cancel_pending_items(pending, sorted(selected))
                )
                selected.clear()
                cursor = _clamp_cursor(cursor, len(pending))
        elif key == "esc":
            failures.extend(
                _cancel_pending_items(pending, list(range(len(pending))))
            )
            pending.clear()
            break
        elif key == ":":
            command = console_input.read_command_line("命令 > ")
            if command is None:
                continue
            success_count, message, done = _execute_pending_command(
                command,
                pending,
                selected,
                success_count=success_count,
                failures=failures,
            )
            cursor = _clamp_cursor(cursor, len(pending))
            if done:
                break

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


def _copy_failure_lines_to_clipboard(
    failures: list[InboundFailure | OutboundFailure],
) -> None:
    if not failures:
        return
    text = failure_lines_for_clipboard(failures)
    if copy_to_clipboard(text):
        print(f"已复制 {len(failures)} 条失败条目到剪贴板（仅原始行，无错误说明）")
    else:
        print("复制失败，请手动复制失败明细中的原始行")


def _process_inbound_batch(lines: list[str]) -> None:
    parsed_usernames: list[str] = []
    for line in lines:
        try:
            username, _, _, _, _ = parse_account_line(line)
            parsed_usernames.append(username)
        except ValueError:
            continue

    inventory_exists = db.exists_in_inventory_many(parsed_usernames)
    outbound_exists = db.exists_in_outbound_many(parsed_usernames)

    def exists_in_inventory(username: str) -> bool:
        return username in inventory_exists

    def exists_in_outbound(username: str) -> bool:
        return username in outbound_exists

    seen_usernames: set[str] = set()
    pending: list[InboundPending] = []
    failures: list[InboundFailure] = []
    success_count = 0

    for line in lines:
        result = classify_inbound_line(
            line,
            seen_usernames,
            exists_in_inventory=exists_in_inventory,
            exists_in_outbound=exists_in_outbound,
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
                result.url,
            )
            seen_usernames.add(result.username)
            inventory_exists.add(result.username)
            success_count += 1

    if pending:
        approved, cancelled = _review_pending(pending)
        success_count += approved
        failures.extend(cancelled)

    _print_inbound_summary(success_count, failures)
    _copy_failure_lines_to_clipboard(failures)


def _print_outbound_summary(success_count: int, failures: list[OutboundFailure]) -> None:
    print()
    print(f"批量出库完成：成功 {success_count} 条，失败 {len(failures)} 条")
    print(f"当前库存：{db.count_inventory()}")
    if failures:
        print()
        print("失败明细：")
        for i, failure in enumerate(failures, start=1):
            print(f"  {i}. [{failure.reason}]")
            print(f"     {failure.line}")


def _process_outbound_batch(lines: list[str]) -> None:
    parsed_usernames: list[str] = []
    for line in lines:
        try:
            username, _, _, _, _ = parse_account_line(line)
            parsed_usernames.append(username)
        except ValueError:
            continue

    inventory_exists = db.exists_in_inventory_many(parsed_usernames)
    outbound_exists = db.exists_in_outbound_many(parsed_usernames)

    def exists_in_inventory(username: str) -> bool:
        return username in inventory_exists

    def exists_in_outbound(username: str) -> bool:
        return username in outbound_exists

    seen_usernames: set[str] = set()
    failures: list[OutboundFailure] = []
    success_count = 0

    for line in lines:
        result = classify_outbound_line(
            line,
            seen_usernames,
            exists_in_inventory=exists_in_inventory,
            exists_in_outbound=exists_in_outbound,
        )
        if isinstance(result, OutboundFailure):
            failures.append(result)
        elif isinstance(result, OutboundReady):
            if exists_in_inventory(result.username):
                db.outbound_by_username(result.username)
            else:
                db.insert_outbound_record(
                    result.username,
                    result.password,
                    result.email,
                    result.email_password,
                    result.url,
                )
            seen_usernames.add(result.username)
            inventory_exists.discard(result.username)
            outbound_exists.add(result.username)
            success_count += 1

    _print_outbound_summary(success_count, failures)
    _copy_failure_lines_to_clipboard(failures)


def handle_inbound() -> None:
    _print_mode_header("入库录入")
    while True:
        lines = _read_batch_lines_or_exit(
            "请输入账号信息（每行一条，输入空行结束）："
        )
        if lines is None:
            break
        if not lines:
            continue
        _process_inbound_batch(lines)


def handle_outbound_paste() -> None:
    _print_mode_header("出库录入")
    while True:
        lines = _read_batch_lines_or_exit(
            "请输入出库账号信息（每行一条，输入空行结束）："
        )
        if lines is None:
            break
        if not lines:
            continue
        _process_outbound_batch(lines)


def handle_entry() -> None:
    while True:
        print()
        print("========== 录入模式 ==========")
        print(f"当前库存：{db.count_inventory()}")
        print("Esc 返回首页")
        print()
        print("[1] 入库录入")
        print("[2] 出库录入")
        print()
        print("请选择录入类型：", end="", flush=True)
        choice = console_input.read_line_or_exit("")
        if choice is None:
            break
        choice = choice.strip()
        if choice == "1":
            handle_inbound()
            break
        if choice == "2":
            handle_outbound_paste()
            break
        if choice:
            print("无效选项，请输入 1 或 2")


def _print_outbound_success(records: list[dict]) -> None:
    lines = [
        format_account(
            record["username"],
            record["password"],
            record["email"],
            record["email_password"],
            record["url"],
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


def handle_outbound() -> None:
    while True:
        _print_mode_header("出库模式")
        inventory = db.count_inventory()
        if inventory == 0:
            print("当前无库存，无法出库")
            if console_input.read_line_or_exit("") is None:
                break
            continue

        raw = console_input.read_line_or_exit(
            "请输入出库数量（直接回车默认为 1）："
        )
        if raw is None:
            break
        if not raw:
            count = 1
        elif not raw.isdigit() or int(raw) <= 0:
            print("无效数量，请输入正整数")
            continue
        else:
            count = int(raw)

        count = min(count, inventory)
        records = db.outbound_oldest_many(count)
        if not records:
            print("当前无库存，无法出库")
            continue

        _print_outbound_success(records)


def handle_search() -> None:
    while True:
        _print_mode_header("查找模式")
        query = console_input.read_line_or_exit("请输入查找字符串：")
        if query is None:
            break
        if not query:
            print("请输入查找字符串")
            continue

        inventory_hits = db.search_inventory(query)
        if inventory_hits:
            print()
            print(f"找到 {len(inventory_hits)} 条【库存】：")
            for record in inventory_hits:
                line = format_account(
                    record["username"],
                    record["password"],
                    record["email"],
                    record["email_password"],
                    record["url"],
                )
                print(f"  【库存】 {line}")

            if len(inventory_hits) == 1:
                confirm = console_input.read_line_or_exit(
                    "是否出库该账号？(Y/N，直接回车跳过)："
                )
                if confirm is None:
                    break
                if confirm.lower() == "y":
                    record = inventory_hits[0]
                    outbound = db.outbound_by_username(record["username"])
                    if outbound is None:
                        print("出库失败，该账号可能已不在库存中")
                    else:
                        _print_outbound_success([outbound])
            continue

        history_hits = db.search_outbound_history(query)
        if history_hits:
            print()
            print(f"找到 {len(history_hits)} 条【出库历史】：")
            for record in history_hits:
                line = format_account(
                    record["username"],
                    record["password"],
                    record["email"],
                    record["email_password"],
                    record["url"],
                )
                print(f"  【出库历史】 {line}")
            continue

        print("未找到匹配的账号")


def main_loop() -> None:
    try:
        while True:
            render_home(db.count_inventory())
            command = console_input.read_command_line("请输入操作：")
            if command is None:
                print("再见。")
                break
            command = command.lower()
            if command == "0":
                handle_entry()
            elif command == "1":
                handle_outbound()
            elif command == "2":
                handle_search()
            else:
                print("无效命令，请输入 0、1、2")
    except KeyboardInterrupt:
        print()
        print("再见。")
