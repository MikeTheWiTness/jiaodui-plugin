/**
 * 从 DSH 的 preset 选择 roster 中隐藏内部子 agent preset。
 *
 * 子 agent preset 必须注册进 agentPresets，tool-subagent 才能按 id 引用；
 * 但 DSH 0.2.x 的 agent-preset 配置没有 hidden/selectable 字段，注册表会把
 * 所有 preset 都交给选择器和设置页。这里只包装 remoteExportList（UI roster），
 * readDocument / validate 保持原样，子 agent 仍能正常解析。
 *
 * 这是 DSH 增加 hidden 字段前的桥接；过滤只影响展示，不改变 composition。
 */

export const name = 'jiaodui-preset-filter'

/** agentPresets 服务就绪后再安装；两个学科包可同时加载。 */
export const inject = ['agentPresets']

/** 明确列出内部 preset，避免误伤用户自建的 *-unit preset。 */
const HIDDEN_PRESET_IDS = new Set(['jiaodui-unit', 'jiaodui-chemistry-unit'])

const INSTALLED = Symbol.for('jiaodui.preset-filter.installed')

export function apply(ctx) {
  const service = ctx.get('agentPresets')
  if (service === undefined || typeof service.remoteExportList !== 'function') return
  if (!Object.isExtensible(service)) return
  const installed = globalThis[INSTALLED] ??= new WeakSet()
  if (installed.has(service)) return
  const original = service.remoteExportList
  service.remoteExportList = async function () {
    const roster = await original.call(service)
    if (roster === undefined || !Array.isArray(roster.presets)) return roster
    return {
      ...roster,
      presets: roster.presets.filter((preset) => !HIDDEN_PRESET_IDS.has(preset?.id)),
    }
  }
  installed.add(service)
}
