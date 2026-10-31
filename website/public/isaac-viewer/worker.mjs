import {CORNERS,validateWhere,matches,emptyPanel,summarizePaths} from './analysis.mjs';
const cache=new Map(), rawCache=new Map();
const digest=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join('');
async function read(asset, binary=false) {
  const storage=binary ? rawCache : cache;
  if(storage.has(asset.url))return storage.get(asset.url);
  const url=new URL(asset.url,self.location.origin);url.searchParams.set('sha256',asset.sha256);
  const response=await fetch(url);
  if(!response.ok)throw Error(`Could not load recorded data (HTTP ${response.status}).`);
  let bytes=new Uint8Array(await response.arrayBuffer());
  if(bytes.length===asset.bytes && await digest(bytes)===asset.sha256) {
    if(typeof DecompressionStream==='undefined')throw Error('This viewer needs a current browser with gzip decompression support.');
    bytes=new Uint8Array(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer());
  }
  if(bytes.length!==asset.uncompressed_bytes || await digest(bytes)!==asset.uncompressed_sha256)throw Error('Recorded-data checksum mismatch. Reload the page; no unverified values were plotted.');
  const value=binary ? new Float32Array(bytes.buffer,bytes.byteOffset,bytes.byteLength/4) : JSON.parse(new TextDecoder().decode(bytes));
  storage.set(asset.url,value);
  if(binary && storage.size>16)storage.delete(storage.keys().next().value);
  return value;
}
let latest=0;
self.onmessage=async event=>{
 const {id,manifest,where,metric,mode,paths,caseOnly}=event.data;latest=id;
 try {
  validateWhere(where);
  if(!caseOnly&&!manifest.fields.includes(metric))throw Error('Unknown tilt channel.');
  const labels=where.campaign || Object.keys(manifest.groups);
  if(labels.some(label=>!manifest.groups[label]))throw Error('Unknown architecture.');
  const panels=[],selectedCases=[];
  const full=Object.keys(where).every(key=>['campaign','corner'].includes(key));
  for(const label of labels) {
   const group=manifest.groups[label];
   const overview=full && !paths && !caseOnly ? await read(group.overviews[metric][mode]) : null;
   for(const corner of CORNERS) {
    if(latest!==id)return;
    if(where.corner && !where.corner.includes(corner))continue;
    self.postMessage({id,progress:`${label} · corner ${corner}`});
    if(overview) {panels.push({campaign:label,corner,...overview[corner]});continue;}
    const shard=group.corners[corner];
    const rows=await read(shard.cases);
    const ids=rows.flatMap((row,i)=>matches({...row,campaign:label},group.factors,where) ? [i] : []);
    if(caseOnly) {selectedCases.push(...ids.map(i=>({campaign:label,...rows[i]})));continue;}
    if(!ids.length) {panels.push({campaign:label,corner,...emptyPanel(manifest.time_s.length)});continue;}
    const values=await read(shard.tilt[metric],true);
    panels.push({campaign:label,corner,...summarizePaths(values,manifest.time_s.length,rows,ids,mode,paths)});
   }
  }
  if(latest===id)self.postMessage({id,panels,selectedCases,caseOnly});
 } catch(error) {self.postMessage({id,error:error.message});}
};
