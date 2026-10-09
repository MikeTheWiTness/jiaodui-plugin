"""用真 Node 加载插件，验证延迟收集、会话工作区与进程失败返回。"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

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
import { mkdirSync } from 'node:fs';
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
assert.equal(submit.parameters.properties.proposal.properties.corrections.items.additionalProperties,false);
const calc=registered.get('jiaodui_calc_evaluate');
assert.equal(calc.parameters.additionalProperties,false);
assert.deepEqual(calc.parameters.required,['expression']);
const realSpawn=ctx.subprocess.spawn;
ctx.subprocess.spawn=spec=>{requests.push(spec);return {done:Promise.resolve({exitCode:0}),collected:{stdout:{readFrom(){return {text:'{}',lossy:false}}},stderr:{readFrom(){return {text:'',lossy:false}}}}}};
await locate.execute({task_id:'a'.repeat(32),unit_id:'b'.repeat(32),phrase:'木板'},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','unit-locate','--task-id','a'.repeat(32),'--unit-id','b'.repeat(32),'--phrase','木板']);
await unitRead.execute({task_id:'a'.repeat(32),unit_id:'b'.repeat(32),start_line:1,max_lines:2000},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','unit-read','--task-id','a'.repeat(32),'--unit-id','b'.repeat(32),'--start-line','1','--max-lines','2000']);
await calc.execute({expression:'1+2'},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','calc','evaluate','--param','expression="1+2"']);
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
await prepare.execute({operation:'execution-policy',path:'/tmp/mat',execution_mode:'automatic',origin:'user'},exec);
assert.deepEqual(requests.at(-1).argv.slice(1),['--json','execution-policy','/tmp/mat','--mode','automatic','--origin','user']);
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
await assert.rejects(()=>tool.execute({args:['--help']},exec),/pipx install/);
assert.deepEqual(attempted,['/explicit/missing/jiaodui']);
'''
    result = subprocess.run([NODE, "--input-type=module", "-e", script, str(tmp_path.resolve())],
                            cwd=ROOT, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
