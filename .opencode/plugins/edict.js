/**
 * Edict for OpenCode — 三省六部任务编排插件
 *
 * 在每轮 session 通过 system prompt 注入：
 * - 三省六部制度简介与状态机、权限矩阵
 * - 当前项目任务看板状态（基于 edict/edict-tasks.json）
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
 * 检测当前项目下的三省六部任务状态（基于 edict/edict-tasks.json）
 * - 文件不存在 → 尚未初始化
 * - 存在且无任务或全部 Done/Cancelled → 闲置
 * - 存在且有进行中任务 → 列出各状态任务数量
 */
function detectEdictPhase(projectDir) {
  const tasksPath = path.join(projectDir, 'edict', 'edict-tasks.json');
  if (!fs.existsSync(tasksPath)) {
    return '**Edict 任务看板**：尚未初始化。可在项目根目录执行 `python scripts/edict_tasks_init.py --path . [--demo]` 创建 edict/edict-tasks.json。';
  }
  try {
    const raw = fs.readFileSync(tasksPath, 'utf8');
    const data = JSON.parse(raw);
    const tasks = Array.isArray(data) ? data : (data.tasks || []);
    if (tasks.length === 0) {
      return '**Edict 任务看板**：edict/edict-tasks.json 已存在，当前无任务（闲置）。可用 edict_tasks_api.py create "标题" 创建旨意。';
    }
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
      if (byState[s]) parts.push(`${s}: ${byState[s]}`);
    }
    return parts.join(' ');
  } catch {
    return '**Edict 任务看板**：edict/edict-tasks.json 存在但无法解析，请检查格式。';
  }
}

/**
 * 将 edict_tasks_api.py、edict_tasks_init.py 复制到项目的 scripts/ 目录，
 * 并写入 .edict-plugin-root 以便脚本或环境变量 EDICT_AGENT_CONFIG 指向插件根的 agent_config.json。
 */
function copyEdictScripts(directory) {
  try {
    const scriptsDir = path.join(pluginRoot, 'scripts');
    const targetDir = path.join(directory, 'scripts');
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
    // 提示：可通过设置 EDICT_AGENT_CONFIG=<pluginRoot>/agent_config.json 使用权限配置
    const hintPath = path.join(targetDir, '.edict-plugin-root');
    if (!fs.existsSync(hintPath)) {
      fs.writeFileSync(hintPath, pluginRoot, 'utf8');
    }
  } catch {
    // Non-fatal
  }
}

/**
 * 构建注入到 system prompt 的 bootstrap 内容
 */
function getBootstrapContent(directory) {
  const phaseHint = detectEdictPhase(directory);

  const intro = `## 三省六部任务编排（Edict for OpenCode）

你当前处于**三省六部**制度下的任务协作上下文。所有任务流转必须通过**状态机 + 权限矩阵**完成，不得直接修改任务 JSON。

- **太子 (taizi)**：分拣旨意，转中书省
- **中书省 (zhongshu)**：规划方案，拆解任务，提交门下审议
- **门下省 (menxia)**：审议方案，准奏或封驳
- **尚书省 (shangshu)**：派发执行，协调六部
- **六部 (libu/hubu/bingbu/xingbu/gongbu/libu_hr)**：执行具体工作，完成后进入 Review`;

  const stateFlow = `### 状态机（_STATE_FLOW）

| 当前状态   | 下一状态  | 说明 |
|------------|------------|------|
| Pending    | Taizi      | 皇上下旨 → 太子分拣 |
| Taizi      | Zhongshu   | 太子转中书省起草 |
| Zhongshu   | Menxia     | 中书提交门下审议 |
| Menxia     | Assigned   | 门下准奏 → 尚书派发 |
| Assigned   | Doing      | 尚书派发六部执行 |
| Doing      | Review     | 各部完成 → 尚书汇总 |
| Review     | Done       | 全流程完成 |

（另有 Next→Doing；封驳时 Menxia→Zhongshu；Stop/Resume/Cancel 见 API。）`;

  const permission = `### 权限矩阵（allowAgents）

- **taizi** → 仅可调用 zhongshu
- **zhongshu** → 仅可调用 menxia, shangshu
- **menxia** → 仅可调用 shangshu, zhongshu
- **shangshu** → 仅可调用六部（libu, hubu, bingbu, xingbu, gongbu, libu_hr）
- **六部** → 不可越权调用其他 agent`;

  const convention = `### 约定（必须遵守）

1. **任务状态与流转**：只通过 \`edict_tasks_api.py\` 的子命令或 **edict-orchestrator** skill 推进，不要直接 \`read_file\`/\`write_file\` 修改 \`edict/edict-tasks.json\` 的 \`state\`、\`flow_log\`、\`progress_log\`。
2. **调用方式**：在项目根目录执行 \`python scripts/edict_tasks_api.py <cmd> ...\`（若已通过插件复制到当前项目 \`scripts/\`）。创建任务用 \`create "标题"\`；推进状态用 \`advance <task_id> <caller_agent> [--remark "..."]\`；门下审议用 \`review <task_id> menxia approve|reject [--comment "..."]\`；汇报进展用 \`progress <task_id> <caller_agent> "进展说明" [--todos "1.xxx|2.yyy"]\`。
3. **身份**：执行 advance/review/progress 时，\`caller_agent\` 必须与当前任务状态所规定的负责 agent 一致（见状态机与权限矩阵）。`;

  const toolMapping = `### OpenCode 工具映射

- 执行脚本：\`run_terminal_cmd\` 或 \`Bash\` 运行 \`python scripts/edict_tasks_api.py ...\`
- 查看任务：可 \`read_file\` \`edict/edict-tasks.json\` 只读查看；修改状态/流转/进展一律通过上述 API
- 使用 orchestrator：通过 \`skill\` 工具加载 \`edict/edict-orchestrator\`（若已安装），按 SKILL 说明传入 action、task_id、caller_agent 等`;

  return `<EXTREMELY_IMPORTANT>
${intro}

${stateFlow}

${permission}

${convention}

${toolMapping}

---
${phaseHint}
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
