/**
 * Edict for OpenCode — 三省六部任务编排插件
 *
 * 在每轮 session 通过 system prompt 注入：
 * - 三省六部制度简介与状态机、权限矩阵
 * - 当前项目任务看板状态（基于 .edict/edict-tasks.json）
 * - 约定：任务流转只通过 edict-orchestrator skill + edict_tasks_api.py，不直接改 JSON
 *
 * 可选：将 edict_tasks_api.py / edict_tasks_init.py 复制到项目 scripts/ 以便调用
 */

import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const pluginRoot = path.resolve(__dirname, '../..');

/**
 * 检测当前项目下的三省六部任务状态（基于 .edict/edict-tasks.json）
 * - 文件不存在 → 尚未初始化
 * - 存在且无任务或全部 Done/Cancelled → 闲置
 * - 存在且有进行中任务 → 列出各状态任务数量
 */
function detectEdictPhase(projectDir) {
  const tasksPath = path.join(projectDir, '.edict', 'edict-tasks.json');
  if (!fs.existsSync(tasksPath)) {
    return '**Edict 任务看板**：尚未初始化。可在项目根目录执行 `python .edict/scripts/edict_tasks_init.py --path . [--demo]` 创建 .edict/edict-tasks.json。';
  }
  try {
    const raw = fs.readFileSync(tasksPath, 'utf8');
    const data = JSON.parse(raw);
    const tasks = Array.isArray(data) ? data : (data.tasks || []);
    if (tasks.length === 0) {
      return '**Edict 任务看板**：.edict/edict-tasks.json 已存在，当前无任务（闲置）。可用 `python .edict/scripts/edict_tasks_api.py create "标题"` 创建旨意。';
    }
    const STATE_CN = {
      Pending: '待处理', Taizi: '太子分拣', Zhongshu: '中书省起草',
      Menxia: '门下省审议', Assigned: '尚书省派发', Doing: '六部执行中',
      Next: '待执行', Review: '尚书省汇总', Done: '已完成',
      Cancelled: '已取消', Blocked: '已阻塞',
    };
    const byState = {};
    for (const t of tasks) {
      const s = t.state || 'Unknown';
      byState[s] = (byState[s] || 0) + 1;
    }
    const terminal = (byState.Done || 0) + (byState.Cancelled || 0) + (byState.Blocked || 0);
    const active = tasks.length - terminal;
    const parts = [`**Edict 任务看板**：共 ${tasks.length} 条任务（${active} 条进行中）。`];
    const order = ['Pending', 'Taizi', 'Zhongshu', 'Menxia', 'Assigned', 'Doing', 'Next', 'Review', 'Done', 'Cancelled', 'Blocked'];
    for (const s of order) {
      if (byState[s]) parts.push(`${STATE_CN[s] || s}: ${byState[s]}`);
    }
    return parts.join(' ');
  } catch {
    return '**Edict 任务看板**：.edict/edict-tasks.json 存在但无法解析，请检查格式。';
  }
}

/**
 * 将 edict_tasks_api.py、edict_tasks_init.py 复制到项目的 .edict/scripts/ 目录，
 * 并写入 .edict-plugin-root 以便脚本定位插件根的 agent_config.json。
 */
function copyEdictScripts(directory) {
  try {
    const scriptsDir = path.join(pluginRoot, 'scripts');
    const targetDir = path.join(directory, '.edict', 'scripts');
    if (!fs.existsSync(targetDir)) {
      fs.mkdirSync(targetDir, { recursive: true });
    }
    for (const name of ['edict_tasks_api.py', 'edict_tasks_init.py']) {
      const src = path.join(scriptsDir, name);
      const dst = path.join(targetDir, name);
      if (fs.existsSync(src) && path.resolve(src) !== path.resolve(dst)) {
        fs.copyFileSync(src, dst);
      }
    }
    const hintPath = path.join(targetDir, '.edict-plugin-root');
    if (!fs.existsSync(hintPath)) {
      fs.writeFileSync(hintPath, pluginRoot, 'utf8');
    }
  } catch {
    // Non-fatal
  }
}

/**
 * 读取 edict-orchestrator/SKILL.md 并去掉 frontmatter
 */
function loadOrchestratorSkill() {
  const candidates = [
    path.join(pluginRoot, 'skills', 'edict-orchestrator', 'SKILL.md'),
  ];
  const homeDir = process.env.HOME || process.env.USERPROFILE || '';
  if (homeDir) {
    candidates.push(path.join(homeDir, '.config', 'opencode', 'skills', 'edict', 'edict-orchestrator', 'SKILL.md'));
  }
  for (const p of candidates) {
    try {
      if (!fs.existsSync(p)) continue;
      let content = fs.readFileSync(p, 'utf8');
      const match = content.match(/^---\n[\s\S]*?\n---\n([\s\S]*)$/);
      if (match) content = match[1];
      return content.trim();
    } catch { /* skip */ }
  }
  return null;
}

/**
 * 构建注入到 system prompt 的 bootstrap 内容
 */
function getBootstrapContent(directory) {
  const phaseHint = detectEdictPhase(directory);
  const orchestratorContent = loadOrchestratorSkill();

  const directive = `## 三省六部任务编排（Edict for OpenCode）

**IMPORTANT: edict-orchestrator skill 内容已包含在下方，你正在遵循它。不要再通过 skill 工具重复加载 edict-orchestrator。**

你当前处于**三省六部**制度下的任务协作上下文。

### 核心规则（必须严格遵守）

1. **任何用户需求，必须先创建 edict 任务**：收到用户的工作请求后，第一步执行 \`python .edict/scripts/edict_tasks_api.py create "任务标题"\`，获得 task_id。
2. **按状态机推进**：创建后以太子身份 advance → 中书规划 → 门下审议 → 尚书派发 → 六部执行 → Review → Done，每一步都通过 \`edict_tasks_api.py\` 推进，不可跳过。
3. **不要直接开始写代码**：在任务未经过中书规划、门下审议之前，禁止直接进入实现阶段。
4. **所有状态变更**通过 \`python .edict/scripts/edict_tasks_api.py\` 完成，禁止直接修改 \`.edict/edict-tasks.json\`。

### 标准流程（每次收到用户请求时执行）

\`\`\`
1. python .edict/scripts/edict_tasks_api.py create "用户需求标题"        → 获得 TASK_ID
2. python .edict/scripts/edict_tasks_api.py advance TASK_ID taizi --remark "分拣完毕"   → Taizi → Zhongshu
3. 以 zhongshu 身份：分析需求、规划方案、汇报 progress
4. python .edict/scripts/edict_tasks_api.py advance TASK_ID zhongshu --remark "方案提交审议" → Zhongshu → Menxia
5. 以 menxia 身份：审议方案
6. python .edict/scripts/edict_tasks_api.py review TASK_ID menxia approve --comment "准奏"  → Menxia → Assigned
7. python .edict/scripts/edict_tasks_api.py advance TASK_ID shangshu --remark "派发执行"     → Assigned → Doing
8. 以六部身份执行具体工作（写代码/文档/测试等），用 progress 汇报
9. python .edict/scripts/edict_tasks_api.py advance TASK_ID <六部> --remark "执行完毕"       → Doing → Review
10. python .edict/scripts/edict_tasks_api.py advance TASK_ID shangshu --remark "汇总完成"    → Review → Done
\`\`\``;

  const toolMapping = `### OpenCode 工具映射

- 执行脚本：\`run_terminal_cmd\` 或 \`Bash\` 运行 \`python .edict/scripts/edict_tasks_api.py ...\`
- 查看任务：可 \`read_file\` 读取 \`.edict/edict-tasks.json\` 只读查看
- 修改状态/流转/进展：一律通过上述 API

**Skill name format:**
当需要加载各省部 skill 时，通过 OpenCode 的 skill 工具调用: skill({ name: "edict-orchestrator" })
Skills 安装路径: ~/.config/opencode/skills/edict/`;

  let body = `${directive}

${toolMapping}

---
${phaseHint}`;

  if (orchestratorContent) {
    body += `

---
## edict-orchestrator 完整指引（已自动加载）

${orchestratorContent}`;
  }

  return `<EXTREMELY_IMPORTANT>
${body}
</EXTREMELY_IMPORTANT>`;
}

/**
 * OpenCode 插件入口：注册 system transform，注入 bootstrap
 */
export const EdictPlugin = async ({ client, directory }) => {
  copyEdictScripts(directory);
  return {
    'experimental.chat.system.transform': async (_input, output) => {
      const bootstrap = getBootstrapContent(directory);
      if (bootstrap) {
        (output.system ||= []).push(bootstrap);
      }
    }
  };
};

export default EdictPlugin;
