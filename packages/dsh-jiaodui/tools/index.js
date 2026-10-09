/**
 * dsh-jiaodui 的原生工具半侧。
 *
 * 这里只做「argv 透传 + 受管子进程 + 结构化返回」，不含任何校对业务判断：
 * 真正的逻辑在 jiaodui Python 包里（CLI 是永久退路，见 PRD D20/D21）。
 * 本模块刻意不 import 任何 @deepseek-ai/* 包，避免 profile 内解析不到随 DSH
 * 安装的包；只用 Node 内建模块。
 */
import { existsSync, readFileSync, realpathSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { isAbsolute } from 'node:path'

export const name = 'jiaodui-tools'

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

/** 仓库内 venv 的 CLI；包被复制进 profile（而非 file: 链接回仓库）时回退到 PATH 上的 jiaodui。 */
function defaultCommand() {
  try {
    const bundled = fileURLToPath(new URL('../../../.venv/bin/jiaodui', import.meta.url))
    const repositoryCore = fileURLToPath(new URL('../../../jiaodui/cli.py', import.meta.url))
    if (existsSync(repositoryCore) && existsSync(bundled)) return bundled
  } catch {
    // import.meta.url 不可用时保持回退
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
const PROPOSAL_SCHEMA = JSON.parse(
  readFileSync(fileURLToPath(new URL('./proposal-schema.json', import.meta.url)), 'utf8'),
).schema

const TASK_PREPARE_OPERATIONS = ['check-env', 'inspect-source', 'convert', 'split',
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
      return ['check-env']
    case 'inspect-source':
      return ['inspect-source', ...target,
        ...(args.preview_chars === undefined || args.preview_chars === null
          ? [] : ['--preview-chars', String(args.preview_chars)])]
    case 'convert':
      return ['convert', ...target, ...modeFlags,
        ...(args.material_name ? ['--material-name', args.material_name] : [])]
    case 'split':
      return ['split', ...target,
        ...(args.subject ? ['--subject', args.subject] : []), ...modeFlags,
        ...(args.strategy ? ['--strategy', args.strategy] : []),
        ...(args.no_clean ? ['--no-clean'] : [])]
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

function registerStructuredTools(ctx, cliTool) {
  const register = (name, description, parameters, buildArgs) => ctx.tools.register({
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
    properties: { task_id: { type: 'string' }, unit_id: { type: 'string' } },
  }, args => ['unit-snapshot', '--task-id', args.task_id, '--unit-id', args.unit_id])

  register('jiaodui_unit_submit', '校验结构化修改建议并生成、登记完整报告。', {
    type: 'object', additionalProperties: false,
    required: ['task_id', 'unit_id', 'proposal', 'expected_snapshot_sha256'],
    properties: {
      task_id: { type: 'string' }, unit_id: { type: 'string' },
      proposal: PROPOSAL_SCHEMA, expected_snapshot_sha256: { type: 'string' },
      preview: { type: 'boolean', default: false },
    },
  }, args => ['unit-submit', '--task-id', args.task_id, '--unit-id', args.unit_id,
    '--proposal-json', JSON.stringify(args.proposal), '--expected-snapshot-sha256',
    args.expected_snapshot_sha256, ...(args.preview ? ['--preview'] : [])])

  register('jiaodui_unit_recovery', '按失败错误码消费一次有限恢复预算；类别由错误码确定性决定。', {
    type: 'object', additionalProperties: false,
    required: ['task_id', 'unit_id', 'fingerprint'],
    properties: {
      task_id: { type: 'string' }, unit_id: { type: 'string' },
      error_code: {
        type: 'string',
        description: '失败的工具/宿主错误码（如 usage / not_found / calc_failed / verify_failed / images.missing / host-timeout）。类别由它决定；未分类码会被拒绝。',
      },
      category: {
        type: 'string',
        enum: ['call_correction', 'calc_representation', 'report_repair',
          'targeted_review', 'technical_redispatch', 'image_schema_fix'],
        description: '只用于父代理判断类的 targeted_review；错误驱动的恢复必须给 error_code，给了 category 就必须与映射一致。',
      },
      fingerprint: { type: 'string', pattern: '^[0-9a-f]{64}$' },
    },
  }, args => ['unit-recovery', '--task-id', args.task_id, '--unit-id', args.unit_id,
    ...(args.error_code ? ['--error-code', args.error_code] : []),
    ...(args.category ? ['--category', args.category] : []),
    '--fingerprint', args.fingerprint])

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

  register('jiaodui_unit_event', '记录单元阶段心跳及取消发起者/原因。', {
    type: 'object', additionalProperties: false,
    required: ['task_id', 'unit_id', 'phase', 'attempt_id'],
    properties: {
      task_id: { type: 'string' }, unit_id: { type: 'string' }, attempt_id: { type: 'string' },
      agent_id: { type: 'string' },
      phase: { type: 'string', enum: ['prepared', 'read', 'images', 'calculated', 'proposed',
        'self_checked', 'verified', 'registered', 'parent_reviewed', 'deliverable'] },
      cancel_initiator: { type: 'string', enum: ['user', 'parent', 'host'] },
      cancel_reason: { type: 'string', enum: ['user_cancel', 'technical_timeout', 'superseded'] },
    },
  }, args => ['unit-event', '--task-id', args.task_id, '--unit-id', args.unit_id,
    '--phase', args.phase, '--attempt-id', args.attempt_id,
    ...(args.agent_id ? ['--agent-id', args.agent_id] : []),
    ...(args.cancel_initiator ? ['--cancel-initiator', args.cancel_initiator] : []),
    ...(args.cancel_reason ? ['--cancel-reason', args.cancel_reason] : [])])

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
        description: '位置参数：inspect-source/convert 传源文件；split 传 raw md；precheck-split/status 传单元根目录（units/<材料名>）；execution-policy 传材料目录。',
      },
      preview_chars: {
        type: 'integer', minimum: 0, maximum: 2000,
        description: '仅 inspect-source：有限正文节选字符数（默认不返回正文）。',
      },
      material_name: { type: 'string', description: '仅 convert：材料目录名。' },
      subject: { type: 'string', enum: ['高中物理'], description: '仅 split：学科。' },
      mode: { type: 'string', enum: ['lecture', 'exam'], description: '仅 convert/split：材料类型。' },
      mode_origin: {
        type: 'string', enum: ['user', 'structure', 'preview', 'confirmed'],
        description: '仅 convert/split：材料类型判断来源。',
      },
      mode_reason: { type: 'string', description: '仅 convert/split：类型判断的简短依据（不超过500字符）。' },
      strategy: { type: 'string', enum: ['rule', 'manual', 'none'], description: '仅 split：拆分策略，默认 rule。' },
      no_clean: { type: 'boolean', description: '仅 split：跳过讲义导入清理（六步全不执行）。' },
      execution_mode: {
        type: 'string', enum: ['automatic', 'interactive'],
        description: '仅 execution-policy：本轮执行模式。',
      },
      origin: { type: 'string', enum: ['user', 'confirmed'], description: '仅 execution-policy：模式来源。' },
    },
  }, taskPrepareArgs)

  ctx.tools.register({
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
      type: 'string', enum: ['高中物理'], description: '可选学科，用于校验学科工具白名单并注入物理量表。',
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
 * @param config - command（CLI 路径或 PATH 名）、timeoutMs、maxOutputBytes。
 */
export function apply(ctx, config = {}) {
  const command = typeof config.command === 'string' && config.command.length > 0 ? config.command : undefined
  const timeoutMs = Number.isFinite(config.timeoutMs) && config.timeoutMs > 0 ? config.timeoutMs : 180000
  const maxOutputBytes = Number.isFinite(config.maxOutputBytes) && config.maxOutputBytes > 0 ? config.maxOutputBytes : 65536

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
      if (!executable) throw new Error('jiaodui: 未找到 CLI，请使用 Python 3.12 的 pipx install <jiaodui wheel>，并安装 pandoc；可用 python3 -m jiaodui 诊断安装')
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
        env: { JIAODUI_WORK_ROOT: cwd },
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
  ctx.tools.register(cliTool)
  registerStructuredTools(ctx, cliTool)
}
