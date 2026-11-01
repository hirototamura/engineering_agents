// A projection of the exact One-Piece references; links are responsibilities,
// not claims that a component satisfies or verifies a requirement.
const modelNodes=Object.fromEntries([...model.requirements,...model.parameters,...model.verification_cases,...(model.functions||[]),...(model.products||[])].map(r=>[r.id,r]));
const components=(model.products||[]).filter(r=>r.data.record_role==='component');
const obligations=model.requirements.filter(r=>r.data.record_role==='requirement');
const review=model.review_decision?.data, baseline=model.baseline;
$('model-summary').innerHTML=`<p><strong>${esc(model.revision)}</strong> · ${esc(model.profile.status)} / ${esc(model.profile.approval_state)}</p><p>${obligations.length} ${L('obligations','要求義務')} · ${model.requirements.length-obligations.length} ${L('groups','グループ')} · ${(model.functions||[]).length} ${L('functions','機能')} · ${components.length} ${L('components','構成品')} · ${model.parameters.length} ${L('parameters','パラメータ')}</p><p class="caption">${review?`${L('Human review','人によるレビュー')}: ${esc(review.reviewed_on)} · ${esc(review.reviewer.id)}<br>`:''}${baseline?`${L('Requirements/allocation baseline','要求・割当のベースライン')}: <code>${esc(refText(baseline))}</code><br>`:''}${L('Review approval is separate from test execution and hardware-design adoption.','レビュー承認は、試験の実施や実機設計の採用とは別の状態です。')}</p>`;
const label=r=>recordText(r,'name')||r.id;
const allocations=r=>(r.links||[]).filter(e=>e.type==='allocate');
const resolveNode=ref=>{const r=modelNodes[ref.id];if(!r||r.revision!==ref.revision)throw new Error(`Missing exact model node ${refText(ref)}`);return r};

function allocationGraph(requirementRecord){
 const graph=$('system-graph');graph.replaceChildren();
 const targets=allocations(requirementRecord).map(e=>resolveNode(e.target));
 const functions=targets.filter(r=>r.kind==='function');
 const products=[...new Map([...targets.filter(r=>r.kind==='product'),...functions.flatMap(r=>allocations(r).map(e=>resolveNode(e.target)))].map(r=>[r.id,r])).values()];
 const height=Math.max(290,products.length*92+68,functions.length*92+68);graph.setAttribute('viewBox',`0 0 840 ${height}`);
 const positions=new Map([[requirementRecord.id,[8,height/2-35]]]);
 functions.forEach((r,i)=>positions.set(r.id,[294,60+i*(height-140)/Math.max(1,functions.length-1)]));
 products.forEach((r,i)=>positions.set(r.id,[580,60+i*(height-140)/Math.max(1,products.length-1)]));
 // Single rows sit at the center; multiple rows retain space for long labels.
 if(functions.length===1)positions.set(functions[0].id,[294,height/2-35]);
 if(products.length===1)positions.set(products[0].id,[580,height/2-35]);
 node(graph,'text',{x:8,y:24,fill:'#24566d'},L('Requirement','要求'));
 node(graph,'text',{x:294,y:24,fill:'#24566d'},L('Responsible function','担当する機能'));
 node(graph,'text',{x:580,y:24,fill:'#24566d'},L('Responsible product / component','担当製品・構成品'));
 const defs=node(graph,'defs'),marker=node(defs,'marker',{id:'allocation-arrow',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:6,markerHeight:6,orient:'auto'});node(marker,'path',{d:'M0 0L10 5L0 10',fill:'#24566d'});
 for(const r of [requirementRecord,...functions])for(const edge of allocations(r)){
  const a=positions.get(r.id),b=positions.get(edge.target.id);if(!a||!b)continue;
  const path=node(graph,'path',{d:`M${a[0]+248},${a[1]+35} C${a[0]+270},${a[1]+35} ${b[0]-22},${b[1]+35} ${b[0]},${b[1]+35}`,fill:'none',stroke:'#899498','stroke-width':1.6,'marker-end':'url(#allocation-arrow)','data-source':r.id,'data-target':edge.target.id,'data-relation':'allocate'});
  node(path,'title',{},`${refText(r)} — allocate → ${refText(edge.target)}`);
 }
 for(const r of [requirementRecord,...functions,...products]){
  const [x,y]=positions.get(r.id),group=node(graph,'g',{'data-record-id':r.id,'data-revision':r.revision});
  node(group,'title',{},`${refText(r)}: ${label(r)}`);
  node(group,'rect',{x,y,width:248,height:70,rx:3,fill:'#faf9f5',stroke:r.kind==='requirement'?'#b64628':'#24566d'});
  node(group,'text',{x:x+10,y:y+19,fill:'#24566d','font-size':12},r.id.replace('cube.component.','').replace('cube.function.',''));
  const words=label(r).split(' ');let lines=[''];for(const word of words){const last=lines.length-1;if((lines[last]+' '+word).length>31&&lines[last])lines.push(word);else lines[last]+=(lines[last]?' ':'')+word}
  lines.slice(0,2).forEach((line,i)=>node(group,'text',{x:x+10,y:y+40+i*17,fill:'#202d34','font-size':12},line));
 }
 if(!targets.length)node(graph,'text',{x:294,y:height/2,fill:'#5b686e'},L('No allocation on this group','このグループに割当はありません'));
}

$('model-architecture').innerHTML=table([L('Function','機能'),L('Requirement IDs','要求ID'),L('Allocated components','割当先の構成品'),L('Boundary','境界')],(model.functions||[]).map(r=>[`<code>${esc(r.id)}</code><br>${esc(label(r))}`,r.data.requirement_ids.map(esc).join(', '),allocations(r).map(e=>`<code>${esc(e.target.id)}</code><br>${esc(label(resolveNode(e.target)))}`).join('<br>'),esc(r.data.boundary)]))+
 table([L('Component','構成品'),L('Parent product','親製品'),L('Scope','対象範囲')],components.map(r=>[`<code>${esc(r.id)}</code><br>${esc(label(r))}`,`<code>${esc(refText(r.data.parent_product_ref))}</code>`,esc(r.data.boundary||r.data.scope)]));
$('model-provenance').textContent=JSON.stringify({model_ref:{id:model.model_record.id,revision:model.revision},snapshot_ref:model.snapshot_ref,baseline_ref:baseline?{id:baseline.id,revision:baseline.revision}:null,review:review?{reviewed_on:review.reviewed_on,reviewer:review.reviewer,scope:review.scope,excluded_scope:review.excluded_scope}:null,source:model.source},null,2);
$('requirement-select').innerHTML=model.requirements.map(r=>`<option value="${esc(r.id)}" ${r.id==='R-HOLD'?'selected':''}>${esc(r.id)} · ${esc(recordText(r,'name'))}</option>`).join('');
function requirement(){
 const r=reqById[$('requirement-select').value],d=r.data,criterion=d.acceptance_criteria,caseRef=d.verification_case_ref,sourceRef=D.runs[1].frozen_requirement_refs.find(x=>x.id===r.id);
 allocationGraph(r);
 const allocationNames=allocations(r).map(e=>`<code>${esc(refText(e.target))}</code><br>${esc(label(resolveNode(e.target)))}`).join('<br>');
 $('requirement-detail').innerHTML=`<h4>${esc(recordText(r,'name'))}</h4><p>${esc(recordText(r,'statement')||L('Organizational group; no independent test obligation.','整理用グループ。独立した試験義務はありません。'))}</p><dl><dt>${L('Record identity','要求のID・版')}</dt><dd><code>${esc(refText(r))}</code></dd><dt>${L('Wording / approval','文面 / 承認')}</dt><dd>${esc(d.status)} / ${esc(d.approval_state)}</dd><dt>${L('Allocated responsibility','担当する機能・製品')}</dt><dd>${allocationNames||L('No direct allocation on this group','グループに直接の割当なし')}</dd><dt>${L('Verification status','検証の状態')}</dt><dd>${esc(d.verification_status)}</dd><dt>${L('Physical verification','実機での検証')}</dt><dd>${d.hardware_verification_required?L('Not demonstrated on hardware','実機では未実証'):L('Hardware test not specified for this node','このノードに実機試験の指定なし')} · physical_verified=${esc(d.physical_verified)}</dd><dt>${L('Planned check','計画した確認')}</dt><dd>${criterion?.metric?`${esc(criterion.metric)} ${esc(criterion.operator)} ${criterion.limit_ref?esc(refText(criterion.limit_ref)):esc(format(criterion.value))} ${esc(criterion.unit)}`:esc(L('Group / conditions remain to be defined','グループ / 条件は未確定'))}${caseRef?`<br><code>${esc(refText(caseRef))}</code>`:''}</dd><dt>${L('Actual campaign input','実際の実行入力')}</dt><dd>${sourceRef?`<code>${esc(refText(sourceRef))}</code>`:L('This node was not in the archived snapshot.','このノードは保存された実行入力にはありません。')}</dd></dl><p class="caption">${esc((JA?d.translations?.ja?.conditions:d.conditions)?.join(' ')||'')}</p><details><summary>${L('Exact links and unresolved items','厳密なリンクと未解決事項')}</summary><pre>${esc(JSON.stringify({links:r.links,unresolved_items:JA?d.translations?.ja?.unresolved_items:d.unresolved_items},null,2))}</pre></details>`;
}
$('requirement-select').addEventListener('change',requirement);requirement();
