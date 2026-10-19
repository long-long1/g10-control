import test from 'node:test';
import assert from 'node:assert/strict';
import {canFinish,statusLabel} from '../src/setup_state.ts';
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
