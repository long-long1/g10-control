import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {buildSync} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const require=createRequire(import.meta.url);
const code=buildSync({entryPoints:[fileURLToPath(new URL('../src/SetupWizard.tsx',import.meta.url))],bundle:true,write:false,platform:'node',format:'cjs',external:['react','react/jsx-runtime']}).outputFiles[0].text;
const mod={exports:{}};
new Function('require','module','exports',code)(require,mod,mod.exports);
const {SetupWizard}=mod.exports;
function state(step=0){return {service:{running:false},setup:{step,completed:false,ready:false,statuses:Array(5).fill('not_checked'),environment:[],data_directory:'X:/Portable/data',portable:false,fallback_reason:'权限不足'},device_setup:{state:'not_checked',message:'请扫描',selected:null,compatible:false,candidates:[],busy:false},audio_route:{state:'missing',message:'证明缺失',validated:false,pair:null,verified_at:null,proof_path:'X:/Portable/data/audio/route-proof.json',confirmation_token:null}};}
function render(s){
 const forbidden=()=>{throw Error('Render cannot invoke hardware operations');};
 return renderToStaticMarkup(React.createElement(SetupWizard,{state:s,busy:false,onStep:forbidden,onEnvironment:forbidden,onScan:forbidden,onSelect:forbidden,onCompatibility:forbidden,onDetectAudio:forbidden,onVerify:forbidden,onFinish:forbidden,onLater:forbidden}));
}
test('all five steps render without invoking any backend operation',()=>{
 for(let step=0;step<5;step++)assert.match(render(state(step)),new RegExp(`第 ${step+1} / 5 步`));
});
test('missing route leaves verification and completion disabled',()=>{
 assert.match(render(state(3)),/button[^>]*disabled=""[^>]*>确认并验证路由/);
 assert.match(render(state(4)),/button[^>]*disabled=""[^>]*>完成配置/);
});
test('all live gates enable completion without claiming already completed',()=>{
 const s=state(4);s.setup.ready=true;s.setup.statuses=Array(5).fill('passed');
 const html=render(s);
 assert.match(html,/关键检查通过，可以完成配置/);
 assert.doesNotMatch(html,/button[^>]*disabled=""[^>]*>完成配置/);
 assert.doesNotMatch(html,/配置已完成。/);
});
test('environment errors, actual data directory and fallback remain visible',()=>{
 const s=state();s.setup.environment=[{name:'WebView2',passed:false,detail:'请手动安装'}];
 const html=render(s);
 for(const text of ['X:/Portable/data','LocalAppData','权限不足','WebView2','请手动安装'])assert.ok(html.includes(text));
});
