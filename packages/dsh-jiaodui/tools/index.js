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

  register('jiaodui_unit_recovery', '按单元与错误类别消费一次有限恢复预算。', {
    type: 'object', additionalProperties: false,
    required: ['task_id', 'unit_id', 'category', 'fingerprint'],
    properties: {
      task_id: { type: 'string' }, unit_id: { type: 'string' },
      category: { type: 'string', enum: ['call_correction', 'calc_representation', 'report_repair',
        'targeted_review', 'technical_redispatch', 'image_schema_fix'] },
      fingerprint: { type: 'string', pattern: '^[0-9a-f]{64}$' },
    },
  }, args => ['unit-recovery', '--task-id', args.task_id, '--unit-id', args.unit_id,
    '--category', args.category, '--fingerprint', args.fingerprint])

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

  for (const [operation, schema] of Object.entries(CALC_SCHEMAS)) {
    const parameters = structuredClone(schema.parameters)
    parameters.properties.subject = {
      type: 'string', enum: ['高中物理'], description: '可选学科，用于校验学科工具白名单并注入物理量表。',
    }
    register(`jiaodui_calc_${operation}`, schema.description, parameters, args => {
      const { subject, ...values } = args
      const params = Object.entries(values).flatMap(([key, value]) => ['--param', `${key}=${JSON.stringify(value)}`])
      return ['calc', operation, ...(subject ? ['--subject', subject] : []), ...params]
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
        const cancelled = new Error('jiaodui: 用户已取消')
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
          const cancelled = new Error('jiaodui: 用户已取消')
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
          const cancelled = new Error('jiaodui: 用户已取消')
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
