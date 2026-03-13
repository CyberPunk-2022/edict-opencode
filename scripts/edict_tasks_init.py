#!/usr/bin/env python3
"""
初始化 edict-tasks.json：在指定目录创建空任务列表或一条 demo 任务。
供 OpenCode 项目首次启用三省六部时使用。

用法:
  python edict_tasks_init.py [--path DIR] [--demo]
  --path  输出目录，默认当前目录；会在该目录下创建 .edict/edict-tasks.json
  --demo  写入一条 Pending 状态的示例任务
"""

import argparse
import json
import os
from datetime import datetime, timezone


def default_scheduler():
    return {
        "enabled": True,
        "stallThresholdSec": 180,
        "maxRetry": 1,
        "retryCount": 0,
        "escalationLevel": 0,
        "lastProgressAt": None,
        "stallSince": None,
        "lastDispatchStatus": None,
        "snapshot": None,
    }


def new_task(task_id: str, title: str, priority: str = "normal") -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "id": task_id,
        "title": title,
        "official": "",
        "org": "太子",
        "state": "Pending",
        "priority": priority,
        "block": "无",
        "reviewRound": 0,
        "_prev_state": None,
        "output": "",
        "ac": "",
        "flow_log": [],
        "progress_log": [],
        "_scheduler": default_scheduler(),
        "archived": False,
        "now": "待太子分拣",
        "updatedAt": now,
    }


def main():
    ap = argparse.ArgumentParser(description="Initialize edict-tasks.json for OpenCode edict")
    ap.add_argument("--path", default=".", help="Project root; creates <path>/.edict/edict-tasks.json")
    ap.add_argument("--demo", action="store_true", help="Add one demo task in Pending state")
    args = ap.parse_args()

    root = os.path.abspath(args.path)
    edict_dir = os.path.join(root, ".edict")
    os.makedirs(edict_dir, exist_ok=True)
    out_path = os.path.join(edict_dir, "edict-tasks.json")

    tasks = []
    if args.demo:
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        tasks.append(new_task(f"JJC-{today}-001", "示例旨意：请编写一份简要需求说明", "normal"))

    payload = {"tasks": tasks, "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Created: {out_path} ({len(tasks)} task(s))")


if __name__ == "__main__":
    main()
