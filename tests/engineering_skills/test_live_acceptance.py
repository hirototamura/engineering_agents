import json
from tools.engineering_skills.live_acceptance import inspect_tool_trace


def test_acceptance_requires_matched_successful_tool_events():
    events=[{'type':'tool_use','name':'skill_view','tool_call_id':'s','input':{'name':'cube-gnc-loop-analysis'}},
            {'type':'tool_result','name':'skill_view','tool_call_id':'s','output':json.dumps({'success':True})},
            {'type':'tool_use','name':'terminal','tool_call_id':'t','input':{'command':'ea-engineering run gnc --input example.json --output new'}},
            {'type':'tool_result','name':'terminal','tool_call_id':'t','output':json.dumps({'exit_code':0})}]
    raw='\n'.join(json.dumps(e) for e in events)
    assert all(inspect_tool_trace(raw,'gnc','cube-gnc-loop-analysis').values())
    assert not any(inspect_tool_trace('I used terminal and the tool was successful','gnc','cube-gnc-loop-analysis').values())
    events[-1]['output']=json.dumps({'exit_code':1})
    assert not inspect_tool_trace('\n'.join(json.dumps(e) for e in events),'gnc','cube-gnc-loop-analysis')['calculator_tool_succeeded']
