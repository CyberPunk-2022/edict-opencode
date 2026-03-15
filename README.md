# Edict for OpenCode

在 **OpenCode** 上重建类似 [edict](https://github.com/cft0808/edict) 的「三省六部」多 Agent 编排：状态机 + 权限矩阵 + 可观测 + 可干预，不依赖 OpenClaw / Redis，沿用 [longtaskforagent](https://github.com/suriyel/longtaskforagent) 的插件 + skills + 文件状态模式。

## 快速安装

### macOS / Linux

```bash
curl -fsSL https://raw.githubusercontent.com/CyberPunk-2022/edict-opencode/master/install.sh | bash
```

### Windows（PowerShell，需开发者模式或管理员权限）

```powershell
irm https://raw.githubusercontent.com/CyberPunk-2022/edict-opencode/master/install.ps1 | iex
```

安装完成后**重启 OpenCode** 即可激活。

## 快速开始

在任意项目目录中初始化任务看板：

```bash
python .edict/scripts/edict_tasks_init.py --path . --demo
```

启动 OpenCode，对它说：

> 处理 edict 看板中的待办任务

系统会自动按三省六部流程运转：太子分拣 → 中书规划 → 门下审议 → 尚书派发 → 六部执行 → 完成。

## 目录结构

```
edict-opencode/
  .opencode/plugins/edict.js     # OpenCode 插件（bootstrap 注入 + phase 检测）
  skills/
    edict-orchestrator/           # 状态机执行入口（唯一可改 state 的 skill）
    taizi/                        # 太子：分拣旨意
    zhongshu/                     # 中书省：规划方案
    menxia/                       # 门下省：审议（准奏/封驳）
    shangshu/                     # 尚书省：派发七部、汇总
    libu/ hubu/ bingbu/           # 六部：文档/数据/代码
    xingbu/ gongbu/ libu_hr/      # 六部：测试/基建/协调
    zaochao/                      # 钦天监（早朝官）：简报与情报
  scripts/                          # 源脚本（安装时复制到项目 .edict/scripts/）
    edict_tasks_api.py            # 任务 API（create/advance/review/progress/...）
    edict_tasks_init.py           # 初始化 .edict/edict-tasks.json
  agent_config.json               # 权限矩阵
  docs/DESIGN.md                  # 完整设计文档
  install.sh / install.ps1        # 一键安装脚本
```

## 核心机制

### 状态机

```
Pending → Taizi → Zhongshu → Menxia → Assigned → Doing → Review → Done
                      ↑          |
                      └── 封驳 ──┘
```

### 权限矩阵

- **太子** → 仅可调用中书省
- **中书省** → 仅可调用门下省、尚书省
- **门下省** → 仅可调用尚书省、中书省（封驳回调）
- **尚书省** → 仅可调用七部（礼户兵刑工吏 + 钦天监）
- **六部 + 钦天监** → 不可越权调用其他 agent

### 制度保障

- 所有状态推进通过 `.edict/scripts/edict_tasks_api.py`，不允许直接修改 JSON
- 门下省必审，中书方案不可跳过审议
- 权限校验自动拦截越权调用

## 设计文档

完整设计（迁移路线、插件与 skills 设计、调度系统等）见 **[docs/DESIGN.md](docs/DESIGN.md)**。

## 参考

- [edict](https://github.com/cft0808/edict) — 原「三省六部」多 Agent 框架（基于 OpenClaw）
- [longtaskforagent](https://github.com/suriyel/longtaskforagent) — OpenCode 多会话工程工作流（插件与 skills 结构参考）

## License

MIT
