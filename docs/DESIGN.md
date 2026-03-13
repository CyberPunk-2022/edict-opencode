# Edict for OpenCode — 设计文档

> 本文档记录「在 OpenCode 上重建类似 edict 的三省六部编排」的完整方案，便于后续实现与迭代不遗漏。

---

## 1. 目标与约束

- **目标**：在仅能使用 OpenCode 的环境下，复刻 edict 的「三省六部」多 Agent 协作理念（状态机 + 权限矩阵 + 可观测 + 可干预）。
- **约束**：不依赖 OpenClaw / Redis / 独立后端服务；复用 longtaskforagent 已验证的「插件 + skills + 文件状态」模式。
- **成果目录**：所有实现放在仓库根目录下的 **`edict-opencode/`**，与 `edict`、`longtaskforagent` 并列。

---

## 2. 总体思路（一句话）

用 longtaskforagent 的「插件 + skills + 文件状态」模式，把 edict 的「三省六部状态机 + 权限矩阵 + 调度」搬到 OpenCode；后端/Redis/看板先简化为**本地 JSON 状态 + skills**，观测与干预通过读写在库内的 `edict-tasks.json` 完成。

---

## 3. 三步迁移路线

### 第 1 步：确定在 OpenCode 里的“单机版 edict”形态

| 原 edict 组件 | OpenCode 替代 |
|---------------|----------------|
| DB / EventBus | **文件**：用户项目根下 `.edict/edict-tasks.json`（隐藏目录，不污染项目结构），结构照抄 edict 的 Task Schema（`state` / `org` / `flow_log` / `progress_log` / `_scheduler` 等）。 |
| 各省部 Agent | **Skills**：`edict-opencode/skills/` 下 `taizi`、`zhongshu`、`menxia`、`shangshu`、`libu`、`hubu`、`bingbu`、`xingbu`、`gongbu`、`libu_hr` 等。 |
| 调度/状态机执行 | **`edict-orchestrator` skill**：唯一允许改写任务状态、flow_log、progress_log、_scheduler 的入口；内部逻辑 = 原 `dispatch_for_state` + 权限校验。 |
| kanban_update.py / REST API | **OpenCode 工具**：`read_file` / `write_file` 操作上述 JSON；`update_plan` 可映射为对单任务的 todos 更新；通过 `skill` 工具调用 `edict/*` skills，用 `@mention` 表达“派发给中书/门下/六部”。 |

### 第 2 步：像 longtaskforagent 一样接入 OpenCode

- 在 **`edict-opencode/.opencode/plugins/edict.js`** 实现插件：
  - 使用 `experimental.chat.system.transform` 在 session 开始时向 system prompt 注入 **bootstrap**：
    - 简述「三省六部制度 + 状态机 + 权限矩阵」；
    - 约定：**不得手动随机调用别的 agent，只通过 `edict-orchestrator` + 读写 `edict-tasks.json` 推进状态**；
    - 可选：根据 `edict-tasks.json` 做「当前项目阶段 / 当前任务」探测并写入提示。
  - **Tool Mapping**：说明“派发/推进/汇报”一律通过读写 JSON + 调用 `edict-orchestrator` / 各省部 skill，不造 HTTP/Redis。
- 安装方式与 longtaskforagent 一致：clone 到 `~/.config/opencode/edict-opencode`（或等效路径），在 `~/.config/opencode/plugins/edict.js` 和 `~/.config/opencode/skills/edict` 建立 symlink 指向本仓库的 `edict-opencode` 内对应路径。

### 第 3 步：把 edict 关键逻辑落成 SKILL + 脚本

- **SKILL.md**（由模型“执行”）+ **Python 脚本**（由模型调用）实现：
  - 状态机表 `_STATE_FLOW`、`_STATE_AGENT_MAP`（与 edict 文档一致）；
  - 权限矩阵 `allowAgents`：可维护一份 `edict-opencode/agent_config.json`，与 edict 文档一致；
  - `_scheduler` 字段及 `handle_scheduler_scan` 算法：初版可只做「超时提醒 + 自动重试」，升级/回滚留 TODO；
  - 活动流：flow_log + progress_log（+ 若有 session 日志可后续融合）→ 单任务 activity 汇总。

---

## 4. 目录与文件结构（edict-opencode 下）

```
edict-opencode/
  .opencode/
    plugins/
      edict.js                 # 插件：bootstrap 注入 + phase 检测 + tool 映射
  skills/
    edict-orchestrator/
      SKILL.md                 # 状态机 + 权限执行入口
    taizi/
      SKILL.md
    zhongshu/
      SKILL.md
    menxia/
      SKILL.md
    shangshu/
      SKILL.md
    libu/
      SKILL.md
    hubu/
      SKILL.md
    bingbu/
      SKILL.md
    xingbu/
      SKILL.md
    gongbu/
      SKILL.md
    libu_hr/
      SKILL.md
  scripts/
    edict_tasks_init.py        # 初始化 edict-tasks.json（空列表或 demo 任务）
    edict_tasks_api.py         # 封装读写：状态推进、flow/progress 追加、权限校验
  docs/
    DESIGN.md                  # 本设计文档（方案记录）
  agent_config.json            # 权限矩阵（与 edict 文档一致）
    # 运行期任务状态存放在用户项目 .edict/edict-tasks.json
  README.md                    # 安装与使用说明
  install.sh                   # macOS/Linux 一键安装
  install.ps1                  # Windows 一键安装（可选）
```

说明：运行期 `edict-tasks.json` 存放在用户项目根目录下的 `.edict/edict-tasks.json`，脚本也复制到 `.edict/scripts/`，避免污染用户项目的 `scripts/` 等常规目录。

---

## 5. 插件 `edict.js` 核心思路

参考 `longtaskforagent/.opencode/plugins/long-task.js`，只改三块：

1. **Phase 检测**（基于 `edict-tasks.json` 或约定路径）：
   - 文件不存在 →「尚未初始化」；
   - 存在且所有任务均为 Done/Cancelled →「闲置」；
   - 存在且存在 Taizi/Zhongshu/Menxia/… 等状态 → 提示当前有哪些阶段在运行。
2. **Bootstrap 内容**：
   - 三省六部制度简介 + 状态机表（文字/表格）；
   - 权限矩阵要点：太子→中书→门下→尚书→六部，仅允许按 `allowAgents` 调用；
   - 约定：任何任务流转必须调用 `edict-orchestrator`；各省部只通过读/写任务文件 + 调用 edict skills 工作。
3. **可选**：自动复制 `edict_tasks_api.py` 到当前项目 `.edict/scripts/`，便于在 skills 中固定调用 `python .edict/scripts/edict_tasks_api.py ...`。

---

## 6. `edict-orchestrator` Skill 设计

- **职责**：唯一可执行「状态推进 / 派发 / 写 flow_log、progress_log、_scheduler」的入口。
- **输入**（示例）：
  - `action`: `create` | `advance` | `review` | `stop` | `resume` | `cancel` | `progress` …
  - `task_id`、`caller_agent`（当前执行方），以及按 action 的 payload（如 `comment`、`todos_snapshot` 等）。
- **行为**：
  - 每次用 `read_file` 读任务 JSON；
  - 按 `_STATE_FLOW` 与 `agent_config.json` 做权限校验（可调用 `edict_tasks_api.py can_dispatch_to`）；
  - 更新 state/org/flow_log/progress_log/_scheduler；
  - 用 `write_file` 写回。
- **输出**：返回是否成功、旧/新状态；失败时返回权限或状态机错误原因。

SKILL.md 内写清算法与约束，具体实现放在 `edict_tasks_api.py`，由模型按 SKILL 说明调用脚本。

---

## 7. 各省部 Skill 设计要点

- 每个省部 skill 只做两件事：
  - **业务决策** + **调用 orchestrator**（例如中书：拆解任务 → 调用 `edict-orchestrator` 的 `advance`/`progress`）；
  - **遵守权限**：在 SKILL 中写明「禁止直接改 state、禁止绕过门下直接进 Assigned/Doing」等。
- 差异只在「何时调用 orchestrator、传哪些参数」；状态与流转一律由 orchestrator 统一执行。

---

## 8. 与 longtaskforagent 的集成

- **安装体验统一**：提供 `install.sh` / `install.ps1`，clone 到 `~/.config/opencode/edict-opencode` 并建立 plugins/skills 的 symlink。
- **可选协作**：longtaskforagent 负责单项目内 SRS/Design/TDD/ST；edict-opencode 负责跨任务/跨阶段的编排与治理；某 feature 的 ST 结果可回写到任务 JSON 的 `output` / `resourceSummary` 等字段。

---

## 9. 状态机与权限（与 edict 保持一致）

### 状态流转 _STATE_FLOW

| 当前状态 | 下一状态 | 来自 | 去向 | 说明 |
|----------|----------|------|------|------|
| Pending  | Taizi    | 皇上 | 太子 | 待处理旨意转交太子分拣 |
| Taizi    | Zhongshu | 太子 | 中书省 | 太子分拣完毕，转中书省起草 |
| Zhongshu | Menxia  | 中书省 | 门下省 | 中书省方案提交门下省审议 |
| Menxia   | Assigned | 门下省 | 尚书省 | 门下省准奏，转尚书省派发 |
| Assigned | Doing    | 尚书省 | 六部 | 尚书省开始派发执行 |
| Next     | Doing    | 尚书省 | 六部 | 待执行任务开始执行 |
| Doing    | Review   | 六部 | 尚书省 | 各部完成，进入汇总 |
| Review   | Done     | 尚书省 | 太子 | 全流程完成，回奏太子转报皇上 |

### 权限矩阵 allowAgents（agent_config.json）

- **taizi** → `["zhongshu"]`
- **zhongshu** → `["menxia", "shangshu"]`
- **menxia** → `["shangshu", "zhongshu"]`
- **shangshu** → `["libu", "hubu", "bingbu", "xingbu", "gongbu", "libu_hr"]`
- **六部**（libu, hubu, bingbu, xingbu, gongbu, libu_hr）→ `[]`（不越权调用其他 agent）

---

## 10. 起步顺序（从哪开始重建）

建议**从数据层往上**做，这样插件和 skills 都依赖同一套状态与 API：

| 顺序 | 内容 | 说明 |
|------|------|------|
| **1** | `agent_config.json` | 权限矩阵（id/label/allowAgents），静态配置，无依赖。 |
| **2** | 任务 JSON 约定 + `edict_tasks_init.py` | 定义 `edict-tasks.json` 的 schema，提供初始化脚本（空列表或一条 demo 任务）。 |
| **3** | `edict_tasks_api.py` | 核心：读写任务、`advance` / `flow` / `progress` / `create` / `can_dispatch_to`，所有流转只通过此脚本。 |
| **4** | `.opencode/plugins/edict.js` | 每轮 session 注入 bootstrap + phase 检测，约定「只通过 orchestrator + 任务文件」推进。 |
| **5** | `skills/edict-orchestrator/SKILL.md` | 写清状态机与权限，指导模型何时调用 `edict_tasks_api.py` 的哪些子命令。 |
| **6** | 各省部 skill 占位 | 先建目录和简短 SKILL.md，再按需补全。 |

**下一步**：先完成 1～3（agent_config + init + api），再实现 4～5（插件 + orchestrator skill）。

---

## 11. 后续实现清单（MVP 优先）

1. **MVP 范围**：单机 file-based 状态机 + 权限校验；不做远程 skills、复杂调度（超时/回滚可先 TODO）。
2. **建议优先落地的三份文件**：
   - `edict-opencode/.opencode/plugins/edict.js`（最小可用，参考 long-task.js）；
   - `edict-opencode/skills/edict-orchestrator/SKILL.md`（含状态机 + 权限说明）；
   - `edict-opencode/scripts/edict_tasks_api.py`（读写 .edict/edict-tasks.json、状态推进、flow/progress 追加、can_dispatch_to）。
3. **再补**：各省部 SKILL.md 占位与内容；`edict_tasks_init.py`；`agent_config.json`；README + install 脚本。

---

## 12. 参考文档

- 原 edict 业务与状态机：[edict](https://github.com/cft0808/edict)（三省六部调度架构与状态机设计）
- OpenCode 插件与 skills 参考实现：[longtaskforagent](https://github.com/suriyel/longtaskforagent)（插件 + skills 结构）

---

*文档版本：0.1 | 存放于 edict-opencode/docs/，便于后续实现与迭代不遗漏。*
