"""用真 Node 加载插件，验证延迟收集、会话工作区与进程失败返回。"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node") or "/Users/chouchou/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/node/bin/node"


def test_native_tool_behavior(tmp_path):
    if not Path(NODE).is_file():
        if os.environ.get("CI"):
            pytest.fail("CI 必须安装 Node 并执行插件行为测试")
        pytest.skip("本地缺少 Node")
    script = r'''
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { apply } from './packages/dsh-jiaodui/tools/index.js';
let tool;
const requests=[];
const ctx={tools:{register(t){tool=t}},subprocess:{
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
const cwd=process.argv[1];
apply(ctx,{command:'node',timeoutMs:5000});
const exec={agent:{session:{header:{cwd}}}};
let result=await tool.execute({args:['-e','setTimeout(()=>console.log(process.env.JIAODUI_WORK_ROOT),30)']},exec);
assert.equal(result.stdout.trim(),cwd);assert.equal(result.exitCode,0);assert.equal(requests[0].cwd,cwd);
const second=join(cwd,'B');mkdirSync(second);
let policyCalls=0;
ctx.sandboxPolicy={resolve({session}){policyCalls++;return {workspaceRoot:session.header.cwd}}};
result=await tool.execute({args:['-e','console.log(process.env.JIAODUI_WORK_ROOT)']},{agent:{session:{header:{cwd:second}}}});
assert.equal(result.stdout.trim(),second);assert.equal(requests[1].cwd,second);assert.equal(policyCalls,1);
await assert.rejects(()=>tool.execute({args:['--work-root',second,'--help']},exec),/work-root/);
result=await tool.execute({args:['-e','setTimeout(()=>{console.error("failure");process.exit(4)},30)']},exec);
assert.equal(result.exitCode,4);assert.equal(result.stderr.trim(),'failure');
await assert.rejects(()=>tool.execute({args:['--help']},{}),/工作区/);
apply(ctx,{command:'node',timeoutMs:150});
result=await tool.execute({args:['-e','console.error("started");setInterval(()=>{},1000)']},exec);
assert.equal(result.exitCode,-1);assert.match(result.stderr,/started/);assert.match(result.stderr,/timeout/);
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
