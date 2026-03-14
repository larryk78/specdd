#!/usr/bin/env python3
"""
todo.py — minimal CLI task tracker

Usage:
    python3 todo.py add "buy milk"
    python3 todo.py list
    python3 todo.py done 1
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# DDS-003
STORAGE_PATH = Path.home() / ".tasks.json"


# DDS-003
def load_tasks() -> list[dict]:
    if not STORAGE_PATH.exists():
        return []
    with open(STORAGE_PATH) as f:
        return json.load(f)


# DDS-003
def save_tasks(tasks: list[dict]):
    tmp = STORAGE_PATH.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(tasks, f, indent=2)
    tmp.replace(STORAGE_PATH)


# DDS-001, DDS-002 — DTC-001, DTC-002
def cmd_add(args, tasks: list[dict]):
    next_id = max((t["id"] for t in tasks), default=0) + 1
    task = {
        "id": next_id,
        "text": args.text,
        "done": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    tasks.append(task)
    save_tasks(tasks)
    print(f"Added task {next_id}: {args.text}")


# DDS-001 — DTC-003, DTC-004
def cmd_list(args, tasks: list[dict]):
    if not tasks:
        print("No tasks yet.")
        return
    for t in tasks:
        marker = "[x]" if t["done"] else "[ ]"
        print(f"{t['id']}  {marker}  {t['text']}")


# DDS-001, DDS-004 — DTC-005, DTC-006, DTC-007
def cmd_done(args, tasks: list[dict]):
    task = next((t for t in tasks if t["id"] == args.id), None)
    if task is None:
        print(f"No task with id {args.id}", file=sys.stderr)
        sys.exit(1)
    if task["done"]:
        print("Already done.")
        return
    task["done"] = True
    save_tasks(tasks)
    print(f"Done: {task['text']}")


# DDS-001
def main():
    parser = argparse.ArgumentParser(prog="todo", description="Simple task tracker")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Add a new task")
    p_add.add_argument("text", help="Task description")

    sub.add_parser("list", help="List all tasks")

    p_done = sub.add_parser("done", help="Mark a task complete")
    p_done.add_argument("id", type=int, help="Task id")

    args = parser.parse_args()
    tasks = load_tasks()  # DDS-003

    if args.command == "add":
        cmd_add(args, tasks)
    elif args.command == "list":
        cmd_list(args, tasks)
    elif args.command == "done":
        cmd_done(args, tasks)


if __name__ == "__main__":
    main()
