import test from 'node:test';
import assert from 'node:assert/strict';
import {canFinish,statusLabel,unavailableSnapshot} from '../src/setup_state.ts';
test('all five live statuses are required',()=>{
  assert.equal(canFinish({ready:true,statuses:Array(5).fill('passed')}),true);
  for(const status of ['not_checked','checking','failed','waiting_user']){
    assert.equal(canFinish({ready:true,statuses:['passed','passed','passed',status,'passed']}),false);
  }
});
test('backend ready cannot be inferred from labels',()=>{
  assert.equal(canFinish({ready:false,statuses:Array(5).fill('passed')}),false);
  assert.equal(canFinish({ready:true,statuses:['passed']}),false);
});
test('states have explicit Chinese labels',()=>{
  assert.deepEqual(['not_checked','checking','passed','failed','waiting_user'].map(statusLabel),['未检测','检测中','通过','失败','待用户操作']);
});
test('failed status refresh revokes displayed success without triggering actions or mutating input',()=>{
 const original={service:{running:true,connection:'connected',audio_active:true,cable_level_dbfs:-3},setup:{step:4,ready:true,completed:true,statuses:Array(5).fill('passed')},microphone:{is_active:true,validated:true},device_setup:{compatible:true},audio_route:{validated:true}};
 const failed=unavailableSnapshot(original);
 assert.equal(failed.service.connection,'unknown');assert.equal(failed.service.audio_active,false);
 assert.equal(failed.service.running,true);assert.equal(failed.service.cable_level_dbfs,-120);
 assert.equal(failed.setup.completed,false);assert.equal(canFinish(failed.setup),false);
 assert.equal(failed.device_setup.compatible,false);assert.equal(failed.microphone.validated,false);
 assert.equal(original.service.audio_active,true);assert.equal(original.setup.completed,true);
});
