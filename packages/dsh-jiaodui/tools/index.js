/**
 * dsh-jiaodui 的原生工具半侧。
 *
 * 这里只做「argv 透传 + 受管子进程 + 结构化返回」，不含任何校对业务判断：
 * 真正的逻辑在 jiaodui Python 包里（CLI 是永久退路，见 PRD D20/D21）。
 * 本模块刻意不 import 任何 @deepseek-ai/* 包，避免 profile 内解析不到随 DSH
 * 安装的包；只用 Node 内建模块。
 */
import { existsSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs'
import { homedir, tmpdir } from 'node:os'
import { fileURLToPath } from 'node:url'
import { isAbsolute, join } from 'node:path'

export const name = 'jiaodui-tools'

const BUNDLE_VERSION = JSON.parse(
  readFileSync(fileURLToPath(new URL('../package.json', import.meta.url)), 'utf8'),
).version

/** 依赖宿主平面的工具注册表与子进程服务（两者都在 dsh-base 里随宿主挂载）。 */
export const inject = ['tools', 'subprocess']

const DESCRIPTION = [
  '运行 jiaodui 确定性校对 CLI，参数原样透传，返回退出码与标准输出 / 错误。',
  '命令顺序、入口判断与硬门槛一律以随包 skill 的 SKILL.md 为准，本描述不重复流程策略。',
  '命令速查：check-env / inspect-source / inspect-images / convert / split / precheck-split / slice /',
  'status / verify-report / parse-report / repair-report [--apply] / calc / quantities / build-report / build-docx。',
  '校对判断不要放进这里：它是确定性工具，不会调用任何模型。',
].join(' ')

/** realpathSync 对不存在的路径抛原始 ENOENT，会绕过相邻的中文校验分支；统一转成结构化错误。 */
function realpathOrThrow(target, label) {
  try {
    return realpathSync(target)
  } catch {
    throw new Error('jiaodui: ' + label + '不存在或不可访问：' + target)
  }
}

/** 定位最终用户运行时；安装脚本使用同一目录结构和 bundle 版本。 */
function installedCommand() {
  const versionPath = ['JiaoDuiAgentSkill', 'versions', BUNDLE_VERSION, 'venv']
  if (process.platform === 'win32') {
    const dataRoot = process.env.LOCALAPPDATA || join(homedir(), 'AppData', 'Local')
    return join(dataRoot, ...versionPath, 'Scripts', 'jiaodui.exe')
  }
  if (process.platform === 'darwin') {
    return join(homedir(), 'Library', 'Application Support', ...versionPath, 'bin', 'jiaodui')
  }
  const dataRoot = process.env.XDG_DATA_HOME || join(homedir(), '.local', 'share')
  return join(dataRoot, ...versionPath, 'bin', 'jiaodui')
}

/** 按显式配置 → 版本化最终运行时 → 仓库软链开发环境 → PATH 发现 CLI。 */
function defaultCommand() {
  try {
    const installed = installedCommand()
    if (existsSync(installed)) return installed

    const repositoryRoot = fileURLToPath(new URL('../../../', import.meta.url))
    const scriptsDir = process.platform === 'win32' ? 'Scripts' : 'bin'
    const executableName = process.platform === 'win32' ? 'jiaodui.exe' : 'jiaodui'
    const bundled = join(repositoryRoot, '.venv', scriptsDir, executableName)
    const repositoryCore = join(repositoryRoot, 'jiaodui', 'cli.py')
    if (existsSync(repositoryCore) && existsSync(bundled)) return bundled
  } catch {
    // 环境路径不可用时保持 PATH 回退
  }
  return 'jiaodui'
}

/** 把一次收集读数转成文本，缺失读数为空串。 */
function readText(reader) {
  if (reader === undefined) return { text: '', lossy: false }
  const read = reader.readFrom(0)
  return { text: read?.text ?? '', lossy: Boolean(read?.lossy) }
}

/** 收尾渲染：退出码 + 两路输出，供模型直接阅读。 */
function render(args, value) {
  const argv = Array.isArray(args?.args) ? args.args.join(' ') : ''
  const lines = ['$ jiaodui ' + argv, 'exitCode: ' + value.exitCode]
  if (value.truncated) lines.push('（输出超过上限，已截断）')
  if (value.stdout.length > 0) lines.push('--- stdout ---', value.stdout)
  if (value.stderr.length > 0) lines.push('--- stderr ---', value.stderr)
  return [{ type: 'text', text: lines.join('\n') }]
}

const CALC_SCHEMAS = JSON.parse(
  readFileSync(fileURLToPath(new URL('./calc-schemas.json', import.meta.url)), 'utf8'),
).operations
const SUBMIT_PROPOSAL_SCHEMA = JSON.parse(
  readFileSync(fileURLToPath(new URL('./proposal-schema-v3.json', import.meta.url)), 'utf8'),
).schema
const SUBMIT_PROPOSAL_V2_SCHEMA = JSON.parse(
  readFileSync(fileURLToPath(new URL('./proposal-schema-bind-current.json', import.meta.url)), 'utf8'),
).schema

/**
 * 子代理工具面：unit 只暴露单元读取/定位/快照/提交/恢复/心跳与全部 calc_*。
 * 父侧默认 full；子 preset 通过 `toolset: unit` 使用它。
 */
const UNIT_TOOL_NAMES = new Set([
  'jiaodui_unit_locate',
  'jiaodui_unit_read',
  'jiaodui_unit_snapshot',
  'jiaodui_unit_submit',
  'jiaodui_unit_submit_v2',
  'jiaodui_unit_recovery',
  'jiaodui_unit_event',
])

/** 按 toolset 生成可见性判定；未知取值直接报错，避免拼错后静默放宽。 */
function toolVisible(config) {
  const toolset = config.toolset ?? 'full'
  if (toolset === 'full') return () => true
  if (toolset !== 'unit') throw new Error("jiaodui: toolset 只能是 'full' 或 'unit'")
  return name => UNIT_TOOL_NAMES.has(name) || name.startsWith('jiaodui_calc_')
}

/** 共用工具 schema 接受两门已落地学科；具体配置与工具权限仍由 core 校验。 */
const SUPPORTED_SUBJECTS = ['高中物理', '高中化学']

const TASK_PREPARE_OPERATIONS = ['check-env', 'inspect-source', 'inspect-images', 'convert', 'split',
  'precheck-split', 'status', 'execution-policy']
/** 准备阶段的子命令白名单：与 `jiaodui <command> --help` 实际注册一致。 */

const DELIVERY_OPERATIONS = ['build-report', 'build-docx']
/** 交付阶段的子命令白名单：整卷报告与 Word 批注版。 */

/**
 * 按 operation 拼 argv：未用到的参数一律不传给 CLI，缺参数也不在这里判，
 * 让 CLI 出稳定的用法错误（exit 2）——判断留在 core，壳只做参数搬运。
 */
function taskPrepareArgs(args) {
  const target = args.path ? [args.path] : []
  const modeFlags = [
    ...(args.mode ? ['--mode', args.mode] : []),
    ...(args.mode_origin ? ['--mode-origin', args.mode_origin] : []),
    ...(args.mode_reason ? ['--mode-reason', args.mode_reason] : []),
  ]
  switch (args.operation) {
    case 'check-env':
      // 契约探针：版本号相同不代表内容相同，check-env 必须比对插件期望与核心能力
      return ['check-env',
        '--expect-schema-version', String(SUBMIT_PROPOSAL_SCHEMA.properties.schema_version.const),
        '--expect-bundle-version', BUNDLE_VERSION]
    case 'inspect-source':
      return ['inspect-source', ...target,
        ...(args.preview_chars === undefined || args.preview_chars === null
          ? [] : ['--preview-chars', String(args.preview_chars)])]
    case 'inspect-images':
      return ['inspect-images', ...(args.path ? ['--unit', args.path] : [])]
    case 'convert':
      return ['convert', ...target, ...modeFlags,
        ...(args.material_name ? ['--material-name', args.material_name] : [])]
    case 'split':
      return ['split', ...target,
        ...(args.subject ? ['--subject', args.subject] : []), ...modeFlags,
        ...(args.strategy ? ['--strategy', args.strategy] : []),
        ...(args.out_root ? ['--out-root', args.out_root] : []),
        ...(args.base_name ? ['--base-name', args.base_name] : []),
        ...(args.images_dir ? ['--images-dir', args.images_dir] : []),
        ...(args.no_clean ? ['--no-clean'] : []),
        ...(args.rerun ? ['--rerun'] : []),
        ...(args.replace_units ? ['--replace-units'] : []),
        ...(args.adopt_units ? ['--adopt-units'] : [])]
    case 'precheck-split':
      return ['precheck-split', ...target]
    case 'status':
      return ['status', ...target]
    case 'execution-policy':
      return ['execution-policy', ...target,
        ...(args.execution_mode ? ['--mode', args.execution_mode] : []),
        ...(args.origin ? ['--origin', args.origin] : [])]
    default:
      // schema 的 enum 已限制取值；这里只做防御性兜底，交给 CLI 报非法子命令
      return [args.operation]
  }
}

function registerStructuredTools(ctx, cliTool, visible) {
  const register = (name, description, parameters, buildArgs) => {
    if (!visible(name)) return
    return ctx.tools.register({
      name,
      description,
      parameters,
      output: cliTool.output,
      timeoutMs: cliTool.timeoutMs,
      isConcurrencySafe: cliTool.isConcurrencySafe,
      async execute(args, exec) {
        return cliTool.execute({ args: ['--json', ...buildArgs(args)] }, exec)
      },
    })
  }

  register('jiaodui_unit_locate', '按task/unit身份查询源文短语位置和安全范围。', {
    type: 'object', additionalProperties: false,
    required: ['task_id', 'unit_id', 'phrase'],
    properties: {
      task_id: { type: 'string' }, unit_id: { type: 'string' }, phrase: { type: 'string' },
    },
  }, args => ['unit-locate', '--task-id', args.task_id, '--unit-id', args.unit_id,
    '--phrase', args.phrase])

  register('jiaodui_unit_read', '按task/unit身份分页读取当前单元源文和图片读取清单。', {
    type: 'object', additionalProperties: false,
    required: ['task_id', 'unit_id'],
    properties: {
      task_id: { type: 'string' }, unit_id: { type: 'string' },
      start_line: { type: 'integer', minimum: 1, default: 1 },
      max_lines: { type: 'integer', minimum: 1, maximum: 2000, default: 2000 },
    },
  }, args => ['unit-read', '--task-id', args.task_id, '--unit-id', args.unit_id,
    '--start-line', String(args.start_line ?? 1), '--max-lines', String(args.max_lines ?? 2000)])

  register('jiaodui_unit_snapshot', '读取单元源文、轮次、报告和数据摘要组成的提交版本。', {
    type: 'object', additionalProperties: false,
    required: ['task_id', 'unit_id'],
    properties: {
      task_id: { type: 'string' }, unit_id: { type: 'string' },
      with_proposal: { type: 'boolean', default: false, description: '附带当前提案修订的精简列表，供返修引用 ID。' },
    },
  }, args => ['unit-snapshot', '--task-id', args.task_id, '--unit-id', args.unit_id,
    ...(args.with_proposal ? ['--with-proposal'] : [])])

  const registerSubmit = (name, description, proposalSchema, flags) => {
    if (!visible(name)) return
    ctx.tools.register({
      name,
      description,
      parameters: {
        type: 'object', additionalProperties: false,
        required: ['task_id', 'unit_id', 'proposal', 'expected_snapshot_sha256'],
        properties: {
          task_id: { type: 'string' }, unit_id: { type: 'string' },
          proposal: proposalSchema,
          expected_snapshot_sha256: { type: 'string' },
          preview: { type: 'boolean', default: false },
        },
      },
      output: cliTool.output,
      timeoutMs: cliTool.timeoutMs,
      isConcurrencySafe: cliTool.isConcurrencySafe,
      async execute(args, exec) {
        const tempDir = mkdtempSync(join(tmpdir(), 'jiaodui-submit-'))
        const proposalPath = join(tempDir, 'proposal.json')
        try {
          writeFileSync(proposalPath, JSON.stringify(args.proposal), { encoding: 'utf8', flag: 'wx', mode: 0o600 })
          return await cliTool.execute({ args: ['--json', 'unit-submit', '--task-id', args.task_id,
            '--unit-id', args.unit_id, '--proposal-json-file', proposalPath,
            '--expected-snapshot-sha256', args.expected_snapshot_sha256,
            ...flags, ...(args.preview ? ['--preview'] : [])] }, exec)
        } finally {
          rmSync(tempDir, { recursive: true, force: true })
        }
      },
    })
  }
  registerSubmit('jiaodui_unit_submit',
    '提交 v3 原文修订（old_text/new_text/reason/evidence），由 core 定位、绑定身份并生成、登记完整报告；返修可引用 base_proposal_revision 并撤回旧 ID。expected_snapshot_sha256 执行 CAS 保护。',
    SUBMIT_PROPOSAL_SCHEMA, [])
  registerSubmit('jiaodui_unit_submit_v2',
    '显式兼容 v2 结构化提案；core 在材料锁内绑定身份与源文摘要，expected_snapshot_sha256 执行 CAS 保护。正常提案请用 jiaodui_unit_submit。',
    SUBMIT_PROPOSAL_V2_SCHEMA, ['--bind-current'])

  register('jiaodui_unit_recovery', '按失败错误码消费一次有限恢复预算；类别由错误码确定性决定，fingerprint由core从failure.message/details派生。每个新的恢复动作使用新的attempt_id，并先用相同ID记录unit-event。', {
    type: 'object', additionalProperties: false,
    required: ['task_id', 'unit_id', 'attempt_id', 'failure'],
    properties: {
      task_id: { type: 'string' }, unit_id: { type: 'string' },
      error_code: {
        type: 'string',
        description: '失败的工具/宿主错误码（如 usage / not_found / calc_failed / verify_failed / images.missing / host-timeout）。类别由它决定；给了它时请省略 category。',
      },
      category: {
        type: 'string',
        enum: ['call_correction', 'calc_representation', 'report_repair',
          'targeted_review', 'technical_redispatch', 'image_schema_fix'],
        description: '只用于父代理判断类的 targeted_review。错误驱动的恢复请省略本字段。',
      },
      attempt_id: {
        type: 'string', minLength: 1, maxLength: 200,
        description: '与unit-event一致的幂等键。每个新的恢复动作都用新值；不得复用已用于其他失败或类别的attempt_id。',
      },
      expected_run_id: {
        type: 'string',
        description: 'CAS 防护：与当前轮次不一致即 run-changed（可选）。',
      },
      failure: {
        type: 'object', additionalProperties: false, required: ['message'],
        description: '失败工具返回的稳定错误内容。只复制message/details，不要加入call_id、时间戳或自造哈希。',
        properties: {
          message: { type: 'string', minLength: 1 },
          details: { type: 'object', additionalProperties: true },
        },
      },
    },
  }, args => ['unit-recovery', '--task-id', args.task_id, '--unit-id', args.unit_id,
    '--attempt-id', args.attempt_id,
    ...(args.error_code ? ['--error-code', args.error_code] : []),
    ...(args.category ? ['--category', args.category] : []),
    ...(args.expected_run_id ? ['--expected-run-id', args.expected_run_id] : []),
    '--failure-json', JSON.stringify(args.failure)])

  register('jiaodui_unit_progress', '只读汇总单元心跳：阶段 / attempt / 最后事件时间 / 在途与超时判定。', {
    type: 'object', additionalProperties: false,
    required: ['task_id'],
    properties: {
      task_id: { type: 'string' },
      unit_id: { type: 'string', description: '省略时汇总该材料当前轮次的全部单元。' },
      stale_after_seconds: {
        type: 'integer', minimum: 0, default: 900,
        description: '最后一次事件距今超过该秒数且仍在途 → stale=true。',
      },
    },
  }, args => ['unit-progress', '--task-id', args.task_id,
    ...(args.unit_id ? ['--unit-id', args.unit_id] : []),
    '--stale-after-seconds', String(args.stale_after_seconds ?? 900)])

  register('jiaodui_dispatch_plan', '按滑动窗口给出下一批可派发单元；只读，不派发、不占预算。', {
    type: 'object', additionalProperties: false,
    required: ['task_id'],
    properties: {
      task_id: { type: 'string' },
      window: { type: 'integer', minimum: 1, default: 8, description: '滑动窗口上限，默认 8。' },
    },
  }, args => ['dispatch-plan', '--task-id', args.task_id,
    '--window', String(args.window ?? 8)])

  register('jiaodui_unit_event', '记录单元阶段心跳。取消不在本工具：请用 jiaodui_unit_cancel。', {
    type: 'object', additionalProperties: false,
    required: ['task_id', 'unit_id', 'phase', 'attempt_id'],
    properties: {
      task_id: { type: 'string' }, unit_id: { type: 'string' }, attempt_id: { type: 'string' },
      agent_id: { type: 'string' },
      phase: { type: 'string', enum: ['prepared', 'read', 'images', 'calculated', 'proposed',
        'self_checked', 'verified', 'registered', 'parent_reviewed', 'deliverable'] },
      expected_run_id: {
        type: 'string',
        description: 'CAS 防护：与当前轮次不一致即 run-changed，避免迟到事件写进新轮次（可选）。',
      },
    },
  }, args => ['unit-event', '--task-id', args.task_id, '--unit-id', args.unit_id,
    '--phase', args.phase, '--attempt-id', args.attempt_id,
    ...(args.agent_id ? ['--agent-id', args.agent_id] : []),
    ...(args.expected_run_id ? ['--expected-run-id', args.expected_run_id] : [])])

  // 取消单独成工具，而不是 unit-event 的可选字段：子代理 preset 的 toolset: unit 不含本工具，
  // 单元子代理因此无法自证取消（第 12 讲实测：子代理在正常心跳里填 user/user_cancel，
  // 伪造出 29 条用户取消，让 dispatch-plan 永久 stop=true）。
  register('jiaodui_unit_cancel', '记录或撤销一次显式取消；只应由父代理/宿主调用（子代理不可见）。', {
    type: 'object', additionalProperties: false,
    required: ['task_id', 'unit_id', 'attempt_id', 'initiator', 'reason'],
    properties: {
      task_id: { type: 'string' }, unit_id: { type: 'string' }, attempt_id: { type: 'string' },
      initiator: {
        type: 'string', enum: ['user', 'parent', 'host'],
        description: '取消发起者。user 只配 user_cancel；parent/host 只配 technical_timeout/superseded。',
      },
      reason: {
        type: 'string', enum: ['user_cancel', 'technical_timeout', 'superseded'],
        description: '取消原因；必须与 initiator 配对，否则 cancel-invalid。',
      },
      revoke: {
        type: 'boolean', default: false,
        description: '撤销该单元当前生效的取消（技术性停止后无需开新轮次即可继续派发）；用户取消不可撤销。',
      },
      agent_id: { type: 'string' },
      expected_run_id: {
        type: 'string',
        description: 'CAS 防护：与当前轮次不一致即 run-changed（可选）。',
      },
    },
  }, args => ['unit-cancel', '--task-id', args.task_id, '--unit-id', args.unit_id,
    '--attempt-id', args.attempt_id, '--initiator', args.initiator, '--reason', args.reason,
    ...(args.revoke ? ['--revoke'] : []),
    ...(args.agent_id ? ['--agent-id', args.agent_id] : []),
    ...(args.expected_run_id ? ['--expected-run-id', args.expected_run_id] : [])])

  register('jiaodui_unit_review', '父代理按当前snapshot接受或退回结构化建议。', {
    type: 'object', additionalProperties: false,
    required: ['task_id', 'unit_id', 'expected_snapshot_sha256', 'decision', 'reviewer_id'],
    properties: {
      task_id: { type: 'string' }, unit_id: { type: 'string' },
      expected_snapshot_sha256: { type: 'string' },
      decision: { type: 'string', enum: ['accepted', 'needs_revision'] },
      reviewer_id: { type: 'string' }, issue: { type: 'string' },
    },
  }, args => ['unit-review', '--task-id', args.task_id, '--unit-id', args.unit_id,
    '--expected-snapshot-sha256', args.expected_snapshot_sha256, '--decision', args.decision,
    '--reviewer-id', args.reviewer_id, ...(args.issue ? ['--issue', args.issue] : [])])

  register('jiaodui_task_prepare', '准备阶段：环境预检 / 源文结构 / 转换 / 拆分 / 拆分预检 / 单元状态 / 执行模式登记。', {
    type: 'object', additionalProperties: false,
    required: ['operation'],
    properties: {
      operation: {
        type: 'string', enum: TASK_PREPARE_OPERATIONS,
        description: '要执行的准备步骤；未用到的参数会被忽略，缺失的参数由 CLI 报用法错误。',
      },
      path: {
        type: 'string',
        description: '位置参数：inspect-source/convert 传源文件；inspect-images 传单元目录；split 传 raw md；precheck-split/status 传单元根目录（units/<材料名>）；execution-policy 传材料目录。',
      },
      preview_chars: {
        type: 'integer', minimum: 0, maximum: 2000,
        description: '仅 inspect-source：有限正文节选字符数（默认不返回正文）。',
      },
      material_name: { type: 'string', description: '仅 convert：材料目录名。' },
      subject: { type: 'string', enum: SUPPORTED_SUBJECTS, description: '仅 split：学科。' },
      mode: { type: 'string', enum: ['lecture', 'exam'], description: '仅 convert/split：材料类型。' },
      mode_origin: {
        type: 'string', enum: ['user', 'structure', 'preview', 'confirmed'],
        description: '仅 convert/split：材料类型判断来源。',
      },
      mode_reason: { type: 'string', description: '仅 convert/split：类型判断的简短依据（不超过500字符）。' },
      strategy: { type: 'string', enum: ['rule', 'manual', 'none'], description: '仅 split：拆分策略，默认 rule。' },
      no_clean: { type: 'boolean', description: '仅 split：跳过讲义导入清理（六步全不执行）。' },
      // 第 12 讲实测：这三个开关原先只有 CLI 有，插件没暴露，父代理被迫退回 bash 调
      // `.venv-cli/bin/jiaodui`——既猜路径（`jiaodui` 不在 PATH，先 exit 127），又绕过了
      // 本工具自带的「--work-root 必须等于当前会话工作区」校验。
      rerun: {
        type: 'boolean', default: false,
        description: '仅 split：开启新轮次，旧报告不计为本轮完成。**会重置本轮的执行模式授权**，之后必须重新登记 execution-policy。',
      },
      replace_units: {
        type: 'boolean', default: false,
        description: '仅 split：单元集变化时把陈旧单元归档到 .superseded/<run_id>/（只移动不删除）并更新本轮单元集。',
      },
      adopt_units: {
        type: 'boolean', default: false,
        description: '仅 split：显式接纳当前磁盘单元集，留痕且不删除产物（与 replace_units 互斥，由 CLI 拒绝）。',
      },
      out_root: { type: 'string', description: '仅 split：单元输出根目录。' },
      base_name: { type: 'string', description: '仅 split：产物基名。' },
      images_dir: { type: 'string', description: '仅 split：图片来源目录。' },
      execution_mode: {
        type: 'string', enum: ['automatic', 'interactive'],
        description: '仅 execution-policy：本轮执行模式。',
      },
      origin: { type: 'string', enum: ['user', 'confirmed'], description: '仅 execution-policy：模式来源。' },
    },
  }, taskPrepareArgs)

  if (visible('jiaodui_delivery')) ctx.tools.register({
    name: 'jiaodui_delivery',
    description: [
      '交付阶段：拼接整卷报告（build-report）或生成 Word 批注版（build-docx）。',
      'stdout 是 CLI 的 --json 结果，含 ok / complete 与结构计数（marker_count / anchor_count /',
      'formula_fallback_count / missing_count / over_count / heading_comment_count）；',
      'json 字段是同一份结果的解析副本。只有 complete=true 且 ok=true 才可声称整卷交付完成。',
    ].join(' '),
    parameters: {
      type: 'object', additionalProperties: false,
      required: ['operation', 'paper_dir'],
      properties: {
        operation: { type: 'string', enum: DELIVERY_OPERATIONS },
        paper_dir: { type: 'string', description: '拆分返回的单元根目录 units/<材料名>。' },
      },
    },
    output: {
      schema: {
        type: 'object', additionalProperties: false,
        required: ['exitCode', 'stdout', 'stderr', 'truncated'],
        properties: {
          ...cliTool.output.schema.properties,
          json: {
            type: 'object', additionalProperties: true,
            description: 'stdout 的 JSON 解析副本；stdout 不是 JSON 对象时缺省。',
          },
        },
      },
      render: cliTool.output.render,
    },
    timeoutMs: cliTool.timeoutMs,
    isConcurrencySafe: cliTool.isConcurrencySafe,
    async execute(args, exec) {
      const value = await cliTool.execute(
        { args: ['--json', args.operation, args.paper_dir] }, exec)
      let parsed
      try {
        parsed = JSON.parse(value.stdout)
      } catch {
        parsed = undefined
      }
      // 只做协议转换：解析失败不改变工具结果，也不抛错
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
        ? { ...value, json: parsed }
        : value
    },
  })

  for (const [operation, schema] of Object.entries(CALC_SCHEMAS)) {
    const parameters = structuredClone(schema.parameters)
    parameters.properties.subject = {
      type: 'string', enum: SUPPORTED_SUBJECTS, description: '可选学科，用于校验学科工具白名单并注入物理量表。',
    }
    parameters.properties.task_id = { type: 'string', description: '记录calc证据时的材料task_id。' }
    parameters.properties.unit_id = { type: 'string', description: '记录calc证据时的单元unit_id。' }
    register(`jiaodui_calc_${operation}`, schema.description, parameters, args => {
      if (Boolean(args.task_id) !== Boolean(args.unit_id)) throw new Error('task_id与unit_id必须同时提供')
      const { subject, task_id, unit_id, ...values } = args
      const params = Object.entries(values).flatMap(([key, value]) => ['--param', `${key}=${JSON.stringify(value)}`])
      return ['calc', operation, ...(subject ? ['--subject', subject] : []),
        ...(task_id ? ['--task-id', task_id, '--unit-id', unit_id] : []), ...params]
    })
  }
}

/**
 * 注册 jiaodui 工具。
 * @param ctx - 携带 tools / subprocess 服务的上下文。
 * @param config - command（CLI 路径或 PATH 名）、timeoutMs、maxOutputBytes、
 *   toolset（full 为父侧默认；unit 为单元子代理的封闭工具集）。
 */
export function apply(ctx, config = {}) {
  const command = typeof config.command === 'string' && config.command.length > 0 ? config.command : undefined
  const timeoutMs = Number.isFinite(config.timeoutMs) && config.timeoutMs > 0 ? config.timeoutMs : 180000
  const maxOutputBytes = Number.isFinite(config.maxOutputBytes) && config.maxOutputBytes > 0 ? config.maxOutputBytes : 65536
  const visible = toolVisible(config)

  const cliTool = {
    name: 'jiaodui',
    description: DESCRIPTION,
    parameters: {
      type: 'object',
      additionalProperties: false,
      required: ['args'],
      properties: {
        args: {
          type: 'array',
          items: { type: 'string' },
          description: 'jiaodui 之后的完整参数，按 CLI 原样写成数组，例如 ["status", "<卷目录>"] 或 ["calc", "evaluate", "--param", "expression=1/2+1/3"]。',
        },
        cwd: {
          type: 'string',
          description: '兼容参数；必须与当前会话工作区一致。工作区每次调用从会话取得。',
        },
      },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        required: ['exitCode', 'stdout', 'stderr', 'truncated'],
        properties: {
          exitCode: { type: 'integer', description: '进程退出码；未能取得时为 -1。' },
          stdout: { type: 'string' },
          stderr: { type: 'string' },
          truncated: { type: 'boolean', description: '输出是否超过收集上限。' },
        },
      },
      render,
    },
    timeoutMs,
    isConcurrencySafe: () => false,
    async execute(args, exec) {
      const argv = Array.isArray(args?.args) ? args.args.map(String) : []
      if (argv.length === 0) throw new Error('jiaodui: args 不能为空，例如 ["status", "<卷目录>"]')
      const session = exec?.agent?.session
      const headerCwd = session?.header?.cwd
      if (typeof headerCwd !== 'string' || !isAbsolute(headerCwd)) {
        throw new Error('jiaodui: 当前会话缺少绝对工作区路径，请先打开工作区')
      }
      // 可选服务通过 get 查询；Cordis 会拒绝直接读取未声明 inject 的属性。
      const policy = ctx.get('sandboxPolicy')
      const cwd = realpathOrThrow(policy?.resolve({ session })?.workspaceRoot ?? headerCwd, '当前会话工作区')
      if (args?.cwd && (!isAbsolute(args.cwd) || realpathOrThrow(args.cwd, 'cwd') !== cwd)) throw new Error('jiaodui: cwd 必须等于当前会话工作区绝对路径')
      for (let i = 0; i < argv.length; i++) {
        if (argv[i] === '--work-root' || argv[i].startsWith('--work-root=')) {
          const root = argv[i] === '--work-root' ? argv[++i] : argv[i].slice('--work-root='.length)
          if (!root || !isAbsolute(root) || realpathOrThrow(root, '--work-root') !== cwd) throw new Error('jiaodui: --work-root 必须等于当前会话工作区')
        }
      }
      let executable
      const candidates = command ? [command] : [...new Set([defaultCommand(), 'jiaodui'])]
      for (const candidate of candidates) {
        try {
          executable = await ctx.subprocess.resolveExecutable(candidate)
          if (executable) break
        } catch {
          // 明确配置不回退，自动发现可继续尝试 PATH。
        }
      }
      if (!executable) throw new Error('jiaodui: 未找到 CLI；请用独立 Python 3.12 安装匹配版本 wheel，并在 DSH 插件 command 中配置 CLI 绝对路径（或让 GUI PATH 可发现 CLI）；Pandoc 也必须安装并可执行')
      if (exec?.signal?.aborted) {
        const cancelled = new Error('jiaodui: 宿主已中止调用；取消来源须由编排事件明确记录')
        cancelled.name = 'AbortError'
        throw cancelled
      }
      const timeoutSignal = AbortSignal.timeout(timeoutMs)
      const signals = []
      if (exec?.signal) signals.push(exec.signal)
      signals.push(timeoutSignal)
      const handle = ctx.subprocess.spawn({
        argv: [executable, ...argv],
        cwd,
        env: { JIAODUI_WORK_ROOT: cwd, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' },
        stdio: {
          stdin: 'ignore',
          stdout: { maxBytes: maxOutputBytes },
          stderr: { maxBytes: maxOutputBytes },
        },
        graceMs: 5000,
        signal: signals.length === 1 ? signals[0] : AbortSignal.any(signals),
      })

      try {
        const outcome = await handle.done
        if (exec?.signal?.aborted) {
          const cancelled = new Error('jiaodui: 宿主已中止调用；取消来源须由编排事件明确记录')
          cancelled.name = 'AbortError'
          throw cancelled
        }
        const stdout = readText(handle.collected.stdout)
        const stderr = readText(handle.collected.stderr)
        return {
          exitCode: typeof outcome?.exitCode === 'number' ? outcome.exitCode : -1,
          stdout: stdout.text,
          stderr: stderr.text,
          truncated: stdout.lossy || stderr.lossy,
        }
      } catch (error) {
        if (exec?.signal?.aborted) {
          const cancelled = new Error('jiaodui: 宿主已中止调用；取消来源须由编排事件明确记录')
          cancelled.name = 'AbortError'
          throw cancelled
        }
        const stdout = readText(handle.collected.stdout)
        const stderr = readText(handle.collected.stderr)
        return {
          exitCode: -1,
          stdout: stdout.text,
          stderr: (stderr.text.length > 0 ? stderr.text + '\n' : '') + String(error?.message ?? error),
          truncated: stdout.lossy || stderr.lossy,
        }
      }
    },
  }
  if (visible('jiaodui')) ctx.tools.register(cliTool)
  registerStructuredTools(ctx, cliTool, visible)
}
