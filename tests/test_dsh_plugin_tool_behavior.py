"""用真 Node 加载插件，验证延迟收集、会话工作区与进程失败返回。"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from jiaodui.execution_policy import CATEGORIES

ROOT = Path(__file__).resolve().parents[1]
# 不写死开发者家目录：只认 PATH 上的 node，找不到就按下面的条件跳过（CI 仍要求必须有）。
NODE = shutil.which("node")


def test_native_tool_behavior(tmp_path):
    if not NODE or not Path(NODE).is_file():
        if os.environ.get("CI"):
            pytest.fail("CI 必须安装 Node 并执行插件行为测试")
        pytest.skip("本地缺少 Node")
    script = r'''
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdirSync, readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { apply, inject } from './packages/dsh-jiaodui/tools/index.js';
let tool;
const registered=new Map();
const requests=[];
const services={tools:{register(t){registered.set(t.name,t);if(t.name==='jiaodui')tool=t}},subprocess:{
  async resolveExecutable(){return process.execPath},
  spawn(spec){
    requests.push(spec);
    let stdout='',stderr='';
    const child=spawn(spec.argv[0],spec.argv.slice(1),{cwd:spec.cwd,env:{...process.env,...spec.env}});
    child.stdout.on('data',b=>stdout+=b);
    child.stderr.on('data',b=>stderr+=b);
    const abort=()=>child.kill('SIGTERM');
    spec.signal.addEventListener('abort',abort,{once:true});
    const done=new Promise((resolve,reject)=>{
      child.on('error',reject);
      child.on('close',(exitCode)=>{spec.signal.removeEventListener('abort',abort);
        if(spec.signal.aborted)reject(new Error('timeout'));else resolve({exitCode});});
    });
    return {done,collected:{stdout:{readFrom(){return {text:stdout,lossy:false}}},stderr:{readFrom(){return {text:stderr,lossy:false}}}}};
  }
}};
// 模拟 Cordis：未声明 inject 的属性访问立即抛错；可选服务用 get 查询。
let policyLookups=0;
const ctx=new Proxy({get(name){
  assert.equal(name,'sandboxPolicy');policyLookups++;return services[name];
}},{get(target,prop,receiver){
  if(Reflect.has(target,prop))return Reflect.get(target,prop,receiver);
  if(!inject.includes(prop))throw new Error(`cannot get property "${prop}" without inject`);
  return services[prop];
}});
assert.throws(()=>ctx.sandboxPolicy,/without inject/);
const cwd=process.argv[1];
apply(ctx,{command:'node',timeoutMs:5000});
const exec={agent:{session:{header:{cwd}}}};
let result=await tool.execute({args:['-e','setTimeout(()=>console.log(process.env.JIAODUI_WORK_ROOT),30)']},exec);
assert.equal(result.stdout.trim(),cwd);assert.equal(result.exitCode,0);assert.equal(requests[0].cwd,cwd);
assert.equal(requests[0].env.PYTHONUTF8,'1');assert.equal(requests[0].env.PYTHONIOENCODING,'utf-8');
assert.equal(policyLookups,1);
const second=join(cwd,'B');mkdirSync(second);
let policyCalls=0;
services.sandboxPolicy={resolve({session}){policyCalls++;assert.equal(session,exec.agent.session);return {workspaceRoot:second}}};
result=await tool.execute({args:['-e','console.log(process.env.JIAODUI_WORK_ROOT)']},exec);
assert.equal(result.stdout.trim(),second);assert.equal(requests[1].cwd,second);assert.equal(policyCalls,1);
assert.equal(policyLookups,2);
delete services.sandboxPolicy;
await assert.rejects(()=>tool.execute({args:['--work-root',second,'--help']},exec),/work-root/);
const locate=registered.get('jiaodui_unit_locate');
assert.deepEqual(locate.parameters.required,['task_id','unit_id','phrase']);
const unitRead=registered.get('jiaodui_unit_read');
assert.equal(unitRead.parameters.properties.max_lines.maximum,2000);
const submit=registered.get('jiaodui_unit_submit');
assert.equal(submit.parameters.properties.proposal.type,'object');
assert.equal(submit.parameters.properties.proposal.properties.schema_version.const,2);
assert.equal(submit.parameters.properties.proposal.properties.evidence.additionalProperties,false);
assert.deepEqual(submit.parameters.properties.proposal.properties.evidence.required,['assumptions','symbols','images','calculations']);
assert.deepEqual(submit.parameters.properties.proposal.properties.corrections.items.required,
  ['category','evidence_ids','expected_original','id','location_id','reason','replacement','severity']);
assert.equal(submit.parameters.properties.proposal.properties.corrections.items.additionalProperties,false);
for (const key of ['task_id','unit_id','run_id','source_sha256','body_sha256','proposal_revision']) {
  assert.ok(!submit.parameters.properties.proposal.required.includes(key),`${key}应由snapshot自动绑定`);
}
const calc=registered.get('jiaodui_calc_evaluate');
assert.equal(calc.parameters.additionalProperties,false);
assert.deepEqual(calc.parameters.required,['expression']);
assert.deepEqual(registered.get('jiaodui_task_prepare').parameters.properties.subject.enum,['高中物理','高中化学']);
for (const name of [...registered.keys()].filter(name=>name.startsWith('jiaodui_calc_'))) {
  assert.deepEqual(registered.get(name).parameters.properties.subject.enum,['高中物理','高中化学']);
}
const realSpawn=ctx.subprocess.spawn;
ctx.subprocess.spawn=spec=>{requests.push(spec);return {done:Promise.resolve({exitCode:0}),collected:{stdout:{readFrom(){return {text:'{}',lossy:false}}},stderr:{readFrom(){return {text:'',lossy:false}}}}}};
await locate.execute({task_id:'a'.repeat(32),unit_id:'b'.repeat(32),phrase:'木板'},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','unit-locate','--task-id','a'.repeat(32),'--unit-id','b'.repeat(32),'--phrase','木板']);
await unitRead.execute({task_id:'a'.repeat(32),unit_id:'b'.repeat(32),start_line:1,max_lines:2000},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','unit-read','--task-id','a'.repeat(32),'--unit-id','b'.repeat(32),'--start-line','1','--max-lines','2000']);
await calc.execute({expression:'1+2'},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','calc','evaluate','--param','expression="1+2"']);
let submittedProposal;
const snapshotForSubmit={snapshot_sha256:'d'.repeat(64),run_id:'run-current',source_sha256:'e'.repeat(64),body_sha256:'f'.repeat(64),next_proposal_revision:3};
let proposalTempPath;
ctx.subprocess.spawn=spec=>{
  requests.push(spec);
  const isSnapshot=spec.argv.includes('unit-snapshot');
  const isSubmit=spec.argv.includes('unit-submit');
  if (isSubmit) {
    const fileIndex=spec.argv.indexOf('--proposal-json-file')+1;
    proposalTempPath=spec.argv[fileIndex];
    submittedProposal=JSON.parse(readFileSync(proposalTempPath,'utf8'));
  }
  const text=isSnapshot?JSON.stringify({ok:true,snapshot:snapshotForSubmit}):isSubmit?'{"ok":true,"verified":true}':'{}';
  return {done:Promise.resolve({exitCode:0}),collected:{stdout:{readFrom(){return {text,lossy:false}}},stderr:{readFrom(){return {text:'',lossy:false}}}}};
};
const longEvidenceText='题'.repeat(200000);
await submit.execute({task_id:'a'.repeat(32),unit_id:'b'.repeat(32),expected_snapshot_sha256:'d'.repeat(64),proposal:{schema_version:2,summary:'无问题',corrections:[],evidence:{assumptions:[{id:'e1',text:longEvidenceText,source_locations:[]}],symbols:[],images:{status:'not_applicable',reason:'无图'},calculations:{status:'not_applicable',reason:'无计算'}},self_check:{status:'passed',checks:['no_issue_review'],unresolved:[]}}},exec);
assert.deepEqual(requests.at(-2).argv.slice(1),['--json','unit-snapshot','--task-id','a'.repeat(32),'--unit-id','b'.repeat(32)]);
assert.equal(submittedProposal.task_id,'a'.repeat(32));
assert.equal(submittedProposal.unit_id,'b'.repeat(32));
assert.equal(submittedProposal.run_id,'run-current');
assert.equal(submittedProposal.source_sha256,'e'.repeat(64));
assert.equal(submittedProposal.body_sha256,'f'.repeat(64));
assert.equal(submittedProposal.proposal_revision,3);
assert.ok(!requests.at(-1).argv.includes('--bind-current'));
assert.equal(submittedProposal.evidence.assumptions[0].text.length,200000);
assert.ok(requests.at(-1).argv.join('').length<8192,'提案内容不得进入 argv');
assert.ok(requests.at(-1).argv.includes('--proposal-json-file'));
assert.ok(!requests.at(-1).argv.includes('--proposal-json'));
assert.equal(existsSync(proposalTempPath),false,'提交结束后须清理临时提案文件');
assert.equal(requests.at(-1).argv[requests.at(-1).argv.indexOf('--expected-snapshot-sha256')+1],'d'.repeat(64));
// P4：父侧准备/交付工具必须结构化传参，且只拼真实存在的子命令与参数
const prepare=registered.get('jiaodui_task_prepare');
assert.equal(prepare.parameters.additionalProperties,false);
assert.deepEqual(prepare.parameters.required,['operation']);
assert.ok(!('args' in prepare.parameters.properties));
const delivery=registered.get('jiaodui_delivery');
assert.equal(delivery.parameters.additionalProperties,false);
assert.deepEqual(delivery.parameters.required,['operation','paper_dir']);
assert.deepEqual(delivery.parameters.properties.operation.enum,['build-report','build-docx']);
await prepare.execute({operation:'check-env'},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','check-env']);
await prepare.execute({operation:'inspect-source',path:'/tmp/a.docx',preview_chars:0},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','inspect-source','/tmp/a.docx','--preview-chars','0']);
await prepare.execute({operation:'convert',path:'/tmp/a.docx',mode:'lecture',mode_origin:'user',mode_reason:'嵌套表格'},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','convert','/tmp/a.docx','--mode','lecture','--mode-origin','user','--mode-reason','嵌套表格']);
await prepare.execute({operation:'split',path:'/tmp/a_raw.md',subject:'高中物理',mode:'lecture',strategy:'rule',no_clean:true},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','split','/tmp/a_raw.md','--subject','高中物理','--mode','lecture','--strategy','rule','--no-clean']);
await prepare.execute({operation:'status',path:'/tmp/units'},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','status','/tmp/units']);
await prepare.execute({operation:'precheck-split',path:'/tmp/units'},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','precheck-split','/tmp/units']);
// 第 12 讲实测：split 的 rerun/replace-units/adopt-units 原先只有 CLI 有，父代理被迫退回
// bash（猜绝对路径、绕过 --work-root 校验）才能开新轮次。这里锁住插件的映射。
assert.ok(prepare.parameters.properties.rerun,'task_prepare 缺 rerun');
assert.ok(prepare.parameters.properties.replace_units,'task_prepare 缺 replace_units');
assert.ok(prepare.parameters.properties.adopt_units,'task_prepare 缺 adopt_units');
await prepare.execute({operation:'split',path:'/tmp/a_raw.md',subject:'高中物理',mode:'lecture',rerun:true,replace_units:true},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','split','/tmp/a_raw.md','--subject','高中物理','--mode','lecture','--rerun','--replace-units']);
await prepare.execute({operation:'split',path:'/tmp/a_raw.md',subject:'高中物理',mode:'lecture',adopt_units:true},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','split','/tmp/a_raw.md','--subject','高中物理','--mode','lecture','--adopt-units']);
await prepare.execute({operation:'execution-policy',path:'/tmp/mat',execution_mode:'automatic',origin:'user'},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','execution-policy','/tmp/mat','--mode','automatic','--origin','user']);
// P5b：心跳查询必须只读，且 stale 阈值可按次调整
// 合并后采纳 main 的轮次 CAS：unit-event 必须能传 expected_run_id
const unitEvent=registered.get('jiaodui_unit_event');
assert.equal(unitEvent.parameters.additionalProperties,false);
assert.ok(unitEvent.parameters.properties.expected_run_id,'unit-event 缺 expected_run_id');
// 第 12 讲实测：取消字段曾挂在 unit-event 上，子代理在正常心跳里填 user/user_cancel 伪造取消
assert.ok(!('cancel_initiator' in unitEvent.parameters.properties),'unit-event 不得再暴露 cancel_initiator');
assert.ok(!('cancel_reason' in unitEvent.parameters.properties),'unit-event 不得再暴露 cancel_reason');
await unitEvent.execute({task_id:'a'.repeat(32),unit_id:'b'.repeat(32),phase:'read',attempt_id:'t1',expected_run_id:'r'.repeat(32)},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','unit-event','--task-id','a'.repeat(32),'--unit-id','b'.repeat(32),'--phase','read','--attempt-id','t1','--expected-run-id','r'.repeat(32)]);
// 取消拆成独立工具：只由父代理调用，子代理 preset 的 toolset: unit 对子代理屏蔽
const unitCancel=registered.get('jiaodui_unit_cancel');
assert.equal(unitCancel.parameters.additionalProperties,false);
assert.deepEqual(unitCancel.parameters.required,['task_id','unit_id','attempt_id','initiator','reason']);
assert.deepEqual(unitCancel.parameters.properties.initiator.enum,['user','parent','host']);
assert.deepEqual(unitCancel.parameters.properties.reason.enum,['user_cancel','technical_timeout','superseded']);
await unitCancel.execute({task_id:'a'.repeat(32),unit_id:'b'.repeat(32),attempt_id:'t1',initiator:'parent',reason:'technical_timeout'},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','unit-cancel','--task-id','a'.repeat(32),'--unit-id','b'.repeat(32),'--attempt-id','t1','--initiator','parent','--reason','technical_timeout']);
await unitCancel.execute({task_id:'a'.repeat(32),unit_id:'b'.repeat(32),attempt_id:'t2',initiator:'parent',reason:'technical_timeout',revoke:true},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','unit-cancel','--task-id','a'.repeat(32),'--unit-id','b'.repeat(32),'--attempt-id','t2','--initiator','parent','--reason','technical_timeout','--revoke']);
const progress=registered.get('jiaodui_unit_progress');
assert.equal(progress.parameters.additionalProperties,false);
assert.deepEqual(progress.parameters.required,['task_id']);
await progress.execute({task_id:'a'.repeat(32),stale_after_seconds:60},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','unit-progress','--task-id','a'.repeat(32),'--stale-after-seconds','60']);
await progress.execute({task_id:'a'.repeat(32),unit_id:'b'.repeat(32)},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','unit-progress','--task-id','a'.repeat(32),'--unit-id','b'.repeat(32),'--stale-after-seconds','900']);
// P5c：滑动窗口判据也必须结构化传参
const plan=registered.get('jiaodui_dispatch_plan');
assert.equal(plan.parameters.additionalProperties,false);
assert.deepEqual(plan.parameters.required,['task_id']);
await plan.execute({task_id:'a'.repeat(32),window:4},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','dispatch-plan','--task-id','a'.repeat(32),'--window','4']);
// P5：恢复入口按错误码分类，category 只留给父代理判断类
const recovery=registered.get('jiaodui_unit_recovery');
assert.equal(recovery.parameters.additionalProperties,false);
assert.deepEqual(recovery.parameters.required,['task_id','unit_id','attempt_id','failure']);
// B1 守卫：插件里恢复类别的 enum 必须与 core 的 CATEGORIES 一致（JS 侧无法 import
// Python，容易静默漂移；期望值由 Python 单一源经 argv 注入）。
assert.deepEqual(recovery.parameters.properties.category.enum,JSON.parse(process.argv[2]));
const failure={message:'字段校验失败',details:{missing:['source_sha256']},call_id:'ignored'};
await recovery.execute({task_id:'a'.repeat(32),unit_id:'b'.repeat(32),attempt_id:'t1',error_code:'usage',failure},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','unit-recovery','--task-id','a'.repeat(32),'--unit-id','b'.repeat(32),'--attempt-id','t1','--error-code','usage','--failure-json',JSON.stringify(failure)]);
await recovery.execute({task_id:'a'.repeat(32),unit_id:'b'.repeat(32),attempt_id:'t2',category:'targeted_review',failure:{message:'父审退回'},expected_run_id:'r'.repeat(32)},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','unit-recovery','--task-id','a'.repeat(32),'--unit-id','b'.repeat(32),'--attempt-id','t2','--category','targeted_review','--expected-run-id','r'.repeat(32),'--failure-json',JSON.stringify({message:'父审退回'})]);
// 未提供的可选参数不得拼进 argv（no_clean 省略时不能出现 --no-clean）
await prepare.execute({operation:'split',path:'/tmp/a_raw.md',subject:'高中物理',mode:'lecture'},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','split','/tmp/a_raw.md','--subject','高中物理','--mode','lecture']);
const delivered=await delivery.execute({operation:'build-report',paper_dir:'/tmp/units'},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','build-report','/tmp/units']);
assert.deepEqual(delivered.json,{});
// stdout 不是 JSON 对象时：不伪造 json 字段，也不抛错
const jsonStub=ctx.subprocess.spawn;
ctx.subprocess.spawn=spec=>{requests.push(spec);return {done:Promise.resolve({exitCode:0}),collected:{stdout:{readFrom(){return {text:'not json',lossy:false}}},stderr:{readFrom(){return {text:'',lossy:false}}}}}};
const rawDelivery=await delivery.execute({operation:'build-docx',paper_dir:'/tmp/units'},exec);
assert.equal(rawDelivery.json,undefined);assert.equal(rawDelivery.stdout,'not json');
ctx.subprocess.spawn=jsonStub;
ctx.subprocess.spawn=realSpawn;
result=await tool.execute({args:['-e','setTimeout(()=>{console.error("failure");process.exit(4)},30)']},exec);
assert.equal(result.exitCode,4);assert.equal(result.stderr.trim(),'failure');
await assert.rejects(()=>tool.execute({args:['--help']},{}),/工作区/);
apply(ctx,{command:'node',timeoutMs:150});
result=await tool.execute({args:['-e','console.error("started");setInterval(()=>{},1000)']},exec);
assert.equal(result.exitCode,-1);assert.match(result.stderr,/started/);assert.match(result.stderr,/timeout/);
// 外部取消必须传播取消语义，不能包装成普通技术失败。
const cancelController = new AbortController();
const cancelExec = {...exec, signal: cancelController.signal};
const cancelPromise = tool.execute({args:['-e','setInterval(()=>{},1000)']},cancelExec);
setTimeout(()=>cancelController.abort(),20);
await assert.rejects(cancelPromise, error => error.name === 'AbortError' && /宿主已中止调用/.test(error.message));
// reject 后仍读取完整收集结果，并延后读取截断标记。
ctx.subprocess.spawn=()=>({collected:{stdout:{readFrom(){return {text:'partial',lossy:true}}},stderr:{readFrom(){return {text:'diagnostic',lossy:false}}}},done:Promise.reject(new Error('broken'))});
result=await tool.execute({args:['--help']},exec);
assert.equal(result.stdout,'partial');assert.equal(result.truncated,true);assert.match(result.stderr,/diagnostic\nbroken/);
let attempted=[];
ctx.subprocess.resolveExecutable=async command=>{attempted.push(command);throw new Error('not found')};
apply(ctx,{command:'/explicit/missing/jiaodui'});
await assert.rejects(()=>tool.execute({args:['--help']},exec),/独立 Python 3.12/);
assert.deepEqual(attempted,['/explicit/missing/jiaodui']);
'''
    result = subprocess.run([NODE, "--input-type=module", "-e", script, str(tmp_path.resolve()),
                             json.dumps(list(CATEGORIES))],
                            cwd=ROOT, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("package", ["dsh-jiaodui", "dsh-jiaodui-chemistry"])
def test_unit_toolset_registers_only_child_tools(package):
    """子代理 preset 的 toolset: unit 必须只注册单元工具与 calc_*，不能漏掉父侧工具。"""
    if not NODE or not Path(NODE).is_file():
        if os.environ.get("CI"):
            pytest.fail("CI 必须安装 Node 并执行插件行为测试")
        pytest.skip("本地缺少 Node")
    script = r'''
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
const root = process.argv[1];
const { apply } = await import(pathToFileURL(join(root, 'tools', 'index.js')).href);
const registered = new Map();
const ctx = { tools: { register(definition) { registered.set(definition.name, definition) } } };
apply(ctx, { toolset: 'unit', timeoutMs: 5000 });
const operations = Object.keys(JSON.parse(readFileSync(join(root, 'tools', 'calc-schemas.json'), 'utf8')).operations);
const expected = [
  'jiaodui_unit_locate',
  'jiaodui_unit_read',
  'jiaodui_unit_snapshot',
  'jiaodui_unit_submit',
  'jiaodui_unit_recovery',
  'jiaodui_unit_event',
  ...operations.map(operation => `jiaodui_calc_${operation}`),
].sort();
assert.deepEqual([...registered.keys()].sort(), expected);
for (const forbidden of ['jiaodui', 'jiaodui_delivery', 'jiaodui_unit_cancel',
  'jiaodui_unit_review', 'jiaodui_task_prepare', 'jiaodui_unit_progress',
  'jiaodui_dispatch_plan']) {
  assert.ok(!registered.has(forbidden), `${forbidden} 不应暴露给单元子代理`);
}
assert.throws(() => apply(ctx, { toolset: 'bogus' }), /toolset/);
'''
    result = subprocess.run([NODE, "--input-type=module", "-e", script,
                             str((ROOT / "packages" / package).resolve())],
                            cwd=ROOT, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


def test_repo_venv_cli_discovery_is_platform_specific(tmp_path):
    if not NODE or not Path(NODE).is_file():
        if os.environ.get("CI"):
            pytest.fail("CI 必须安装 Node 并执行插件行为测试")
        pytest.skip("本地缺少 Node")

    repository_root = tmp_path / "release copy (test)"
    package_root = repository_root / "packages" / "dsh-jiaodui"
    tools_dir = package_root / "tools"
    tools_dir.mkdir(parents=True)
    for filename in ("index.js", "calc-schemas.json", "proposal-schema.json"):
        shutil.copy2(ROOT / "packages" / "dsh-jiaodui" / "tools" / filename,
                     tools_dir / filename)
    shutil.copy2(ROOT / "packages" / "dsh-jiaodui" / "package.json",
                 package_root / "package.json")
    (repository_root / "jiaodui").mkdir(parents=True)
    (repository_root / "jiaodui" / "cli.py").write_text("", encoding="utf-8")
    runtime_launchers = {
        "darwin": repository_root / "fake-home" / "Library" / "Application Support"
                  / "JiaoDuiAgentSkill" / "versions" / "0.1.0" / "venv" / "bin" / "jiaodui",
        "win32": repository_root / "fake-local" / "JiaoDuiAgentSkill" / "versions"
                 / "0.1.0" / "venv" / "Scripts" / "jiaodui.exe",
    }
    dev_launchers = {
        "darwin": repository_root / ".venv" / "bin" / "jiaodui",
        "win32": repository_root / ".venv" / "Scripts" / "jiaodui.exe",
    }
    for launcher in [*runtime_launchers.values(), *dev_launchers.values()]:
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_text("", encoding="utf-8")

    script = r'''
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import { join } from 'node:path';
import { promises as fs } from 'node:fs';
const [cwd, modulePath, platformNames] = process.argv.slice(1);
const { apply, inject } = await import(pathToFileURL(modulePath).href);
process.env.HOME=join(cwd,'fake-home');
process.env.USERPROFILE=join(cwd,'fake-home');
process.env.LOCALAPPDATA=join(cwd,'fake-local');
process.env.XDG_DATA_HOME=join(cwd,'fake-xdg');
const attempts=[];
let tool;
const services={tools:{register(value){if(value.name==='jiaodui')tool=value}},subprocess:{
  async resolveExecutable(command){attempts.push(command);return process.execPath},
  spawn(){
    return {done:Promise.resolve({exitCode:0}),collected:{
      stdout:{readFrom(){return {text:'',lossy:false}}},
      stderr:{readFrom(){return {text:'',lossy:false}}},
    }};
  },
}};
const ctx=new Proxy({get(name){return services[name]}},{get(target,prop,receiver){
  if(Reflect.has(target,prop))return Reflect.get(target,prop,receiver);
  if(!inject.includes(prop))throw new Error(`unexpected service ${String(prop)}`);
  return services[prop];
}});
apply(ctx);
const exec={agent:{session:{header:{cwd}}}};
const expected=[];
for(const platform of JSON.parse(platformNames)){
  Object.defineProperty(process,'platform',{value:platform,configurable:true});
  const isWindows=platform==='win32';
  const installed=join(isWindows?process.env.LOCALAPPDATA:process.env.HOME,
    ...(isWindows?[]:['Library','Application Support']),
    'JiaoDuiAgentSkill','versions','0.1.0','venv',
    ...(isWindows?['Scripts','jiaodui.exe']:['bin','jiaodui']));
  const dev=join(cwd,'.venv',isWindows?'Scripts':'bin',isWindows?'jiaodui.exe':'jiaodui');
  await tool.execute({args:['--help']},exec);
  expected.push(installed);
  await fs.rename(installed,installed+'.disabled');
  await tool.execute({args:['--help']},exec);
  expected.push(dev);
  await fs.unlink(dev);
  await tool.execute({args:['--help']},exec);
  expected.push('jiaodui');
}
assert.deepEqual(attempts,expected);
console.log(JSON.stringify(attempts));
'''
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", script, str(repository_root),
         str(tools_dir / "index.js"), json.dumps(["darwin", "win32"])],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=15)
    assert result.returncode == 0, result.stderr
    expected = []
    for platform in ("darwin", "win32"):
        expected.extend((str(runtime_launchers[platform]), str(dev_launchers[platform]), "jiaodui"))
    assert json.loads(result.stdout.strip()) == expected
