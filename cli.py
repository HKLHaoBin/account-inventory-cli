"""Interactive CLI for account inbound/outbound management."""

from __future__ import annotations

import database as db
from parser import format_account, parse_account_line


def render_home(inventory: int) -> None:
    print()
    print("========== 账号出入库管理 ==========")
    print(f"当前库存：{inventory}")
    print()
    print("[0] 录入账号")
    print("    格式：账号----密码----邮箱----邮箱密码")
    print("    前两段必填，后两段可选")
    print()
    print("[1] 出库账号（先进先出，自动复制到剪贴板）")
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


def handle_inbound() -> None:
    print()
    print("请输入账号信息（一行）：", end="", flush=True)
    line = input().strip()
    try:
        username, password, email, email_password = parse_account_line(line)
    except ValueError as exc:
        print(f"录入失败：{exc}")
        return

    if db.exists_in_inventory(username):
        print(f"账号 {username} 已在库存中，录入已取消")
        return

    if db.exists_in_outbound(username):
        latest = db.get_latest_outbound_time(username)
        time_hint = f"（最近出库：{latest}）" if latest else ""
        print(
            f"警告：账号 {username} 曾出现在出库记录中{time_hint}"
        )
        print("是否仍要录入？(y/N): ", end="", flush=True)
        confirm = input().strip()
        if confirm.lower() != "y":
            print("录入已取消")
            return

    try:
        db.insert_account(username, password, email, email_password)
    except ValueError as exc:
        print(str(exc))
        return

    print(f"录入成功，当前库存：{db.count_inventory()}")


def handle_outbound() -> None:
    record = db.outbound_oldest()
    if record is None:
        print("当前无库存，无法出库")
        return

    text = format_account(
        record["username"],
        record["password"],
        record["email"],
        record["email_password"],
    )
    print()
    print("出库成功：")
    print(text)
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
