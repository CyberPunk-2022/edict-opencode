#!/usr/bin/env python3
"""
三省六部任务状态 API（file-based，供 OpenCode skills 调用）

子命令:
  create   <title> [--priority normal]  创建任务，state=Pending
  advance  <task_id> <caller_agent> [--remark "..."]  按状态机推进
  review   <task_id> <caller_agent> approve|reject [--comment "..."]  门下审议
  flow     <task_id> <from_dept> <to_dept> <remark>  仅追加流转记录
  progress <task_id> <caller_agent> <text> [--todos "1.xxx|2.yyy"]  追加进展
  stop     <task_id> <caller_agent> [--reason "..."]  叫停
  resume   <task_id> <caller_agent> [--reason "..."]  恢复
  cancel   <task_id> <caller_agent> [--reason "..."]  取消
  can_dispatch_to <from_agent> <to_agent>  校验权限，退出码 0 表示允许

任务文件路径：当前目录下 .edict/edict-tasks.json，或环境变量 EDICT_TASKS_PATH。
权限配置：脚本所在仓库根目录的 agent_config.json（edict-opencode/agent_config.json）。
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Windows 终端默认 GBK，无法输出 emoji / 部分中文，强制 UTF-8
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# 状态机：当前状态 -> (下一状态, 来自部门名, 去向部门名, 说明)
_STATE_FLOW = {
    "Pending": ("Taizi", "皇上", "太子", "待处理旨意转交太子分拣"),
    "Taizi": ("Zhongshu", "太子", "中书省", "太子分拣完毕，转中书省起草"),
    "Zhongshu": ("Menxia", "中书省", "门下省", "中书省方案提交门下省审议"),
    "Menxia": ("Assigned", "门下省", "尚书省", "门下省准奏，转尚书省派发"),
    "Assigned": ("Doing", "尚书省", "六部", "尚书省开始派发执行"),
    "Next": ("Doing", "尚书省", "六部", "待执行任务开始执行"),
    "Doing": ("Review", "六部", "尚书省", "各部完成，进入汇总"),
    "Review": ("Done", "尚书省", "太子", "全流程完成，回奏太子转报皇上"),
}

# 状态 -> 负责 agent_id（Doing/Next 由 org 推断）；Pending 由太子接旨
_STATE_AGENT_MAP = {
    "Taizi": "taizi",
    "Zhongshu": "zhongshu",
    "Menxia": "menxia",
    "Assigned": "shangshu",
    "Doing": None,
    "Next": None,
    "Review": "shangshu",
    "Pending": "taizi",
}

# 部门名 -> agent_id
_ORG_AGENT_MAP = {
    "礼部": "libu",
    "户部": "hubu",
    "兵部": "bingbu",
    "刑部": "xingbu",
    "工部": "gongbu",
    "吏部": "libu_hr",
    "钦天监": "zaochao",
    "中书省": "zhongshu",
    "门下省": "menxia",
    "尚书省": "shangshu",
}

# 状态 -> 部门显示名
_STATE_ORG_MAP = {
    "Taizi": "太子",
    "Zhongshu": "中书省",
    "Menxia": "门下省",
    "Assigned": "尚书省",
    "Doing": "执行中",
    "Next": "待执行",
    "Review": "尚书省",
    "Done": "完成",
    "Cancelled": "已取消",
    "Blocked": "阻塞",
}

# 状态码 -> 中文显示标签（用户可见输出）
_STATE_LABEL_CN = {
    "Pending": "待处理",
    "Taizi": "太子分拣",
    "Zhongshu": "中书省起草",
    "Menxia": "门下省审议",
    "Assigned": "尚书省派发",
    "Doing": "六部执行中",
    "Next": "待执行",
    "Review": "尚书省汇总",
    "Done": "已完成",
    "Cancelled": "已取消",
    "Blocked": "已阻塞",
}


def _label(state):
    """返回状态的中文标签，格式：中文标签(State)"""
    cn = _STATE_LABEL_CN.get(state, state)
    return f"{cn}({state})"


def _script_dir():
    return Path(__file__).resolve().parent


def _repo_root():
    # 脚本在 edict-opencode/scripts/ 下，仓库根为上级
    return _script_dir().parent


def _find_tasks_path():
    p = os.environ.get("EDICT_TASKS_PATH")
    if p and os.path.isfile(p):
        return p
    cwd = Path.cwd()
    for d in [cwd, cwd.parent]:
        f = d / ".edict" / "edict-tasks.json"
        if f.is_file():
            return str(f)
    return str(cwd / ".edict" / "edict-tasks.json")


def _load_agent_config():
    env_path = os.environ.get("EDICT_AGENT_CONFIG")
    if env_path and os.path.isfile(env_path):
        with open(env_path, encoding="utf-8") as f:
            return json.load(f)
    # 1) 脚本所在目录的 .edict-plugin-root 记录了插件仓库根路径
    hint = _script_dir() / ".edict-plugin-root"
    if hint.is_file():
        plugin_root = Path(hint.read_text(encoding="utf-8").strip())
        cfg = plugin_root / "agent_config.json"
        if cfg.is_file():
            with open(cfg, encoding="utf-8") as f:
                return json.load(f)
    # 2) fallback: 脚本在 edict-opencode/scripts/ 时，上级就是仓库根
    root = _repo_root()
    cfg_path = root / "agent_config.json"
    if cfg_path.is_file():
        with open(cfg_path, encoding="utf-8") as f:
            return json.load(f)
    return {"agents": []}


def _load_tasks(path=None):
    path = path or _find_tasks_path()
    if not os.path.isfile(path):
        return None, path, {"tasks": [], "updatedAt": None}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    tasks = data.get("tasks", []) if isinstance(data, dict) else data
    if isinstance(data, dict):
        return data.get("tasks", []), path, data
    return tasks, path, {"tasks": tasks, "updatedAt": None}


def _save_tasks(path, tasks_list, meta=None):
    meta = meta or {}
    meta["tasks"] = tasks_list
    meta["updatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _find_task(tasks, task_id):
    return next((t for t in tasks if t.get("id") == task_id), None)


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def can_dispatch_to(from_agent: str, to_agent: str) -> bool:
    cfg = _load_agent_config()
    for a in cfg.get("agents", []):
        if a.get("id") == from_agent:
            return to_agent in a.get("allowAgents", [])
    return False


def cmd_can_dispatch(from_agent: str, to_agent: str) -> int:
    ok = can_dispatch_to(from_agent, to_agent)
    cfg = _load_agent_config()
    from_label = next((a.get("label", from_agent) for a in cfg.get("agents", []) if a.get("id") == from_agent), from_agent)
    to_label = next((a.get("label", to_agent) for a in cfg.get("agents", []) if a.get("id") == to_agent), to_agent)
    if ok:
        print(f"✅ 允许：{from_label}({from_agent}) → {to_label}({to_agent})", flush=True)
        return 0
    print(f"🚫 禁止：{from_label}({from_agent}) 无权调用 {to_label}({to_agent})", file=sys.stderr, flush=True)
    return 1


def cmd_create(title: str, priority: str = "normal") -> int:
    tasks_list, path, meta = _load_tasks()
    if tasks_list is None:
        print("ERROR: edict-tasks.json not found. Run edict_tasks_init.py first.", file=sys.stderr)
        return 1
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    seq = 1
    for t in tasks_list:
        tid = t.get("id", "")
        if tid.startswith(f"JJC-{today}-"):
            try:
                n = int(tid.split("-")[-1])
                if n >= seq:
                    seq = n + 1
            except ValueError:
                pass
    task_id = f"JJC-{today}-{seq:03d}"
    now = _now_iso()
    task = {
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
        "flow_log": [{"at": now, "from": "皇上", "to": "太子", "remark": f"下旨：{title}"}],
        "progress_log": [],
        "_scheduler": {"enabled": True, "lastProgressAt": now},
        "archived": False,
        "now": "待太子分拣",
        "updatedAt": now,
    }
    tasks_list.insert(0, task)
    _save_tasks(path, tasks_list, meta)
    print(f"{task_id} | 状态：{_label('Pending')} | 📜 旨意已下达", flush=True)
    return 0


def cmd_advance(task_id: str, caller_agent: str, remark: str = "") -> int:
    tasks_list, path, meta = _load_tasks()
    if tasks_list is None:
        print("ERROR: edict-tasks.json not found.", file=sys.stderr)
        return 1
    task = _find_task(tasks_list, task_id)
    if not task:
        print(f"ERROR: task {task_id} not found.", file=sys.stderr)
        return 1
    state = task.get("state")
    if state in ("Done", "Cancelled"):
        print(f"ERROR: 任务 {task_id} 已处于终态 {_label(state)}，无法推进。", file=sys.stderr)
        return 1
    flow = _STATE_FLOW.get(state)
    if not flow:
        print(f"ERROR: 当前状态 {_label(state)} 无法继续推进。", file=sys.stderr)
        return 1
    next_state, from_dept, to_dept, desc = flow
    # 权限：当前负责该状态的 agent 才能推进（caller 应对应 state 的负责人）
    allowed_agent = _STATE_AGENT_MAP.get(state)
    if allowed_agent is None and state in ("Doing", "Next"):
        allowed_agent = _ORG_AGENT_MAP.get(task.get("org", ""))
    if allowed_agent and caller_agent != allowed_agent:
        cfg = _load_agent_config()
        allowed_label = next((a.get("label", allowed_agent) for a in cfg.get("agents", []) if a.get("id") == allowed_agent), allowed_agent)
        caller_label = next((a.get("label", caller_agent) for a in cfg.get("agents", []) if a.get("id") == caller_agent), caller_agent)
        print(f"ERROR: {_label(state)} 仅允许 {allowed_label}({allowed_agent}) 推进，当前调用者为 {caller_label}({caller_agent})。", file=sys.stderr)
        return 1
    now = _now_iso()
    task["state"] = next_state
    task["org"] = _STATE_ORG_MAP.get(next_state, task.get("org"))
    task["now"] = remark or desc
    task["updatedAt"] = now
    task.setdefault("flow_log", []).append({
        "at": now, "from": from_dept, "to": to_dept, "remark": remark or desc
    })
    _save_tasks(path, tasks_list, meta)
    print(f"{_label(state)} → {_label(next_state)}", flush=True)
    return 0


def cmd_review(task_id: str, caller_agent: str, action: str, comment: str = "") -> int:
    if action not in ("approve", "reject"):
        print("ERROR: action must be approve or reject.", file=sys.stderr)
        return 1
    if caller_agent != "menxia":
        print("ERROR: only menxia can perform review.", file=sys.stderr)
        return 1
    tasks_list, path, meta = _load_tasks()
    if tasks_list is None:
        print("ERROR: edict-tasks.json not found.", file=sys.stderr)
        return 1
    task = _find_task(tasks_list, task_id)
    if not task:
        print(f"ERROR: task {task_id} not found.", file=sys.stderr)
        return 1
    if task.get("state") != "Menxia":
        print(f"ERROR: task must be in Menxia to review, current: {task.get('state')}.", file=sys.stderr)
        return 1
    now = _now_iso()
    if action == "approve":
        task["state"] = "Assigned"
        task["org"] = "尚书省"
        task["now"] = comment or "门下省准奏，转尚书省派发"
        task.setdefault("flow_log", []).append({
            "at": now, "from": "门下省", "to": "尚书省", "remark": comment or "✅ 准奏"
        })
    else:
        task["state"] = "Zhongshu"
        task["org"] = "中书省"
        task["reviewRound"] = task.get("reviewRound", 0) + 1
        task["now"] = comment or "门下省封驳，返回中书省修改"
        task.setdefault("flow_log", []).append({
            "at": now, "from": "门下省", "to": "中书省", "remark": comment or "🚫 封驳"
        })
    task["updatedAt"] = now
    _save_tasks(path, tasks_list, meta)
    result = _label(task["state"])
    if action == "approve":
        print(f"✅ 准奏 → {result}", flush=True)
    else:
        round_n = task.get("reviewRound", 1)
        print(f"🚫 封驳（第{round_n}轮）→ {result}", flush=True)
    return 0


def cmd_flow(task_id: str, from_dept: str, to_dept: str, remark: str) -> int:
    tasks_list, path, meta = _load_tasks()
    if tasks_list is None:
        print("ERROR: edict-tasks.json not found.", file=sys.stderr)
        return 1
    task = _find_task(tasks_list, task_id)
    if not task:
        print(f"ERROR: task {task_id} not found.", file=sys.stderr)
        return 1
    task.setdefault("flow_log", []).append({
        "at": _now_iso(), "from": from_dept, "to": to_dept, "remark": remark
    })
    task["updatedAt"] = _now_iso()
    _save_tasks(path, tasks_list, meta)
    print(f"📋 流转已记录 | {from_dept} → {to_dept}", flush=True)
    return 0


def cmd_progress(task_id: str, caller_agent: str, text: str, todos: str = "") -> int:
    tasks_list, path, meta = _load_tasks()
    if tasks_list is None:
        print("ERROR: edict-tasks.json not found.", file=sys.stderr)
        return 1
    task = _find_task(tasks_list, task_id)
    if not task:
        print(f"ERROR: task {task_id} not found.", file=sys.stderr)
        return 1
    cfg = _load_agent_config()
    label = next((a.get("label", caller_agent) for a in cfg.get("agents", []) if a.get("id") == caller_agent), caller_agent)
    now = _now_iso()
    entry = {
        "at": now,
        "agent": caller_agent,
        "agentLabel": label,
        "text": text,
        "state": task.get("state"),
        "org": task.get("org"),
    }
    if todos:
        items = []
        for part in todos.split("|"):
            part = part.strip()
            if not part:
                continue
            status = "not-started"
            if "✅" in part or "completed" in part.lower():
                status = "completed"
            elif "🔄" in part or "in-progress" in part.lower() or "进行" in part:
                status = "in-progress"
            title = part.replace("✅", "").replace("🔄", "").strip()
            if title.endswith(")"):
                title = title.rsplit("(", 1)[0].strip()
            items.append({"id": str(len(items) + 1), "title": title[:80], "status": status})
        entry["todos"] = items
    task.setdefault("progress_log", []).append(entry)
    task["updatedAt"] = now
    if task.get("_scheduler"):
        task["_scheduler"]["lastProgressAt"] = now
    _save_tasks(path, tasks_list, meta)
    print(f"📝 进展已记录 | {label} → {_label(task.get('state'))}", flush=True)
    return 0


def cmd_stop(task_id: str, caller_agent: str, reason: str = "") -> int:
    tasks_list, path, meta = _load_tasks()
    if tasks_list is None:
        print("ERROR: edict-tasks.json not found.", file=sys.stderr)
        return 1
    task = _find_task(tasks_list, task_id)
    if not task:
        print(f"ERROR: task {task_id} not found.", file=sys.stderr)
        return 1
    if task.get("state") in ("Done", "Cancelled"):
        print("ERROR: 任务已终结，无法叫停。", file=sys.stderr)
        return 1
    prev = task.get("state")
    task["_prev_state"] = prev
    task["state"] = "Blocked"
    task["block"] = reason or "已叫停"
    task["now"] = reason or "已叫停"
    task["updatedAt"] = _now_iso()
    _save_tasks(path, tasks_list, meta)
    print(f"⏸️ 已叫停 | {_label(prev)} → {_label('Blocked')}", flush=True)
    return 0


def cmd_resume(task_id: str, caller_agent: str, reason: str = "") -> int:
    tasks_list, path, meta = _load_tasks()
    if tasks_list is None:
        print("ERROR: edict-tasks.json not found.", file=sys.stderr)
        return 1
    task = _find_task(tasks_list, task_id)
    if not task:
        print(f"ERROR: task {task_id} not found.", file=sys.stderr)
        return 1
    if task.get("state") != "Blocked":
        print("ERROR: 任务未处于阻塞状态，无法恢复。", file=sys.stderr)
        return 1
    prev = task.get("_prev_state") or "Taizi"
    task["state"] = prev
    task["org"] = _STATE_ORG_MAP.get(prev, task.get("org"))
    task["block"] = "无"
    task["now"] = reason or "已恢复"
    task["_prev_state"] = None
    task["updatedAt"] = _now_iso()
    _save_tasks(path, tasks_list, meta)
    print(f"▶️ 已恢复 | {_label('Blocked')} → {_label(prev)}", flush=True)
    return 0


def cmd_cancel(task_id: str, caller_agent: str, reason: str = "") -> int:
    tasks_list, path, meta = _load_tasks()
    if tasks_list is None:
        print("ERROR: edict-tasks.json not found.", file=sys.stderr)
        return 1
    task = _find_task(tasks_list, task_id)
    if not task:
        print(f"ERROR: task {task_id} not found.", file=sys.stderr)
        return 1
    prev = task.get("state")
    task["state"] = "Cancelled"
    task["now"] = reason or "已取消"
    task["updatedAt"] = _now_iso()
    task.setdefault("flow_log", []).append({
        "at": task["updatedAt"], "from": task.get("org", ""), "to": "-", "remark": reason or "任务取消"
    })
    _save_tasks(path, tasks_list, meta)
    print(f"❌ 已取消 | {_label(prev)} → {_label('Cancelled')}", flush=True)
    return 0


def main():
    ap = argparse.ArgumentParser(description="Edict tasks API (file-based)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    # create
    p = sub.add_parser("create")
    p.add_argument("title")
    p.add_argument("--priority", default="normal")
    # advance
    p = sub.add_parser("advance")
    p.add_argument("task_id")
    p.add_argument("caller_agent")
    p.add_argument("--remark", default="")
    # review
    p = sub.add_parser("review")
    p.add_argument("task_id")
    p.add_argument("caller_agent")
    p.add_argument("action", choices=["approve", "reject"])
    p.add_argument("--comment", default="")
    # flow
    p = sub.add_parser("flow")
    p.add_argument("task_id")
    p.add_argument("from_dept")
    p.add_argument("to_dept")
    p.add_argument("remark", nargs="?", default="")
    # progress
    p = sub.add_parser("progress")
    p.add_argument("task_id")
    p.add_argument("caller_agent")
    p.add_argument("text")
    p.add_argument("--todos", default="")
    # stop / resume / cancel
    for name in ("stop", "resume", "cancel"):
        p = sub.add_parser(name)
        p.add_argument("task_id")
        p.add_argument("caller_agent")
        p.add_argument("--reason", default="")
    # can_dispatch_to
    p = sub.add_parser("can_dispatch_to")
    p.add_argument("from_agent")
    p.add_argument("to_agent")

    args = ap.parse_args()
    cmd = args.cmd

    if cmd == "create":
        return cmd_create(args.title, getattr(args, "priority", "normal"))
    if cmd == "advance":
        return cmd_advance(args.task_id, args.caller_agent, getattr(args, "remark", ""))
    if cmd == "review":
        return cmd_review(args.task_id, args.caller_agent, args.action, getattr(args, "comment", ""))
    if cmd == "flow":
        return cmd_flow(args.task_id, args.from_dept, args.to_dept, getattr(args, "remark", "") or "")
    if cmd == "progress":
        return cmd_progress(args.task_id, args.caller_agent, args.text, getattr(args, "todos", ""))
    if cmd == "stop":
        return cmd_stop(args.task_id, args.caller_agent, getattr(args, "reason", ""))
    if cmd == "resume":
        return cmd_resume(args.task_id, args.caller_agent, getattr(args, "reason", ""))
    if cmd == "cancel":
        return cmd_cancel(args.task_id, args.caller_agent, getattr(args, "reason", ""))
    if cmd == "can_dispatch_to":
        return cmd_can_dispatch(args.from_agent, args.to_agent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
