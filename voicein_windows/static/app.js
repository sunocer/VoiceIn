const $=id=>document.getElementById(id);
let config=null,codexTasks=[];
const taskLabel=t=>{
  const folder=(t.cwd||'').split(/[\\/]/).filter(Boolean).pop()||'无项目路径';
  const time=t.updatedAt?new Date(t.updatedAt).toLocaleString():'';
  return (t.title||t.id)+' · '+folder+(time?' · '+time:'');
};
function showTask(task,message){
  $('threadHelp').textContent=message||(task?('任务 ID：'+task.id+'；项目：'+(task.cwd||'未知')):'可手工填写 UUID');
}
async function loadTasks(autoFill=true){
  $('refreshThreads').disabled=true;$('threadHelp').textContent='正在扫描本机 Codex 任务…';
  try{
    const r=await fetch('/api/codex/tasks');const result=await r.json().catch(()=>({}));
    if(!r.ok||!result.ok)throw Error(result.message||'扫描失败');
    codexTasks=result.tasks||[];
    const select=$('threadSelect');select.replaceChildren();
    const manual=document.createElement('option');manual.value='';manual.textContent='手工输入任务 ID';select.append(manual);
    for(const task of codexTasks){const option=document.createElement('option');option.value=task.id;option.textContent=taskLabel(task);select.append(option);}
    const saved=$('threadId').value.trim();
    const match=codexTasks.find(t=>t.id===saved);
    if(match){select.value=match.id;showTask(match,'已匹配已保存任务：'+taskLabel(match));}
    else if(!saved&&autoFill&&codexTasks.length){
      select.value=codexTasks[0].id;$('threadId').value=codexTasks[0].id;
      showTask(codexTasks[0],'已自动填入最近任务，请确认标题后点击“保存配置”：'+taskLabel(codexTasks[0]));
    }else{select.value='';showTask(null,codexTasks.length?'已发现 '+codexTasks.length+' 个任务；请选择任务':'没有发现可用任务，可手工填写 UUID');}
  }catch(e){$('threadSelect').replaceChildren(new Option('自动发现不可用',''));showTask(null,'自动发现失败：'+e.message+'；仍可手工填写 UUID');}
  finally{$('refreshThreads').disabled=false;}
}
async function load(){
  const r=await fetch('/api/config');if(!r.ok)throw Error('无法读取配置');config=await r.json();
  for(const id of ['auth','resource','endpoint','threadId','recordHotkey','modeHotkey'])$(id).value=config[id]||'';
  for(const id of ['itn','punc','ddc','autoFollowCodex'])$(id).checked=!!config[id];
  document.querySelector(`input[name=output][value=${config.output}]`).checked=true;
  $('auth').dispatchEvent(new Event('change'));
  const saved=[];
  if(config.configured?.appid)saved.push('AppID '+(config.appidHint||'已保存'));
  if(config.configured?.token)saved.push('Access Token 已保存');
  if(config.configured?.apikey)saved.push('API Key 已保存');
  if(config.threadId)saved.push('Codex 任务 '+config.threadId.slice(0,8)+'…');
  $('saved').textContent=saved.length?'长期配置：'+saved.join(' / '):'尚未保存识别凭据';
  $('configMeta').textContent='配置文件：'+(config.configPath||'Windows 用户配置目录')+'；录音键：'+(config.recordHotkey||'F8');
  for(const id of ['appid','token','apikey'])if(config.configured?.[id])$(id).placeholder='已安全保存；留空表示不修改';
  await loadTasks(true);
}
$('auth').onchange=()=>{$('legacy').hidden=$('auth').value!=='legacy';$('modern').hidden=$('auth').value!=='apikey';};
$('threadSelect').onchange=()=>{const task=codexTasks.find(t=>t.id===$('threadSelect').value);if(task){$('threadId').value=task.id;showTask(task,'已选择：'+taskLabel(task));}else showTask(null,'手工输入模式');};
$('threadId').oninput=()=>{if($('threadSelect').value!==$('threadId').value)$('threadSelect').value='';};
$('refreshThreads').onclick=()=>loadTasks(true);
$('save').onclick=async()=>{
  const body={auth:$('auth').value,resource:$('resource').value.trim(),endpoint:$('endpoint').value,
    threadId:$('threadId').value.trim(),recordHotkey:$('recordHotkey').value.trim(),modeHotkey:$('modeHotkey').value.trim(),output:document.querySelector('input[name=output]:checked').value,
    itn:$('itn').checked,punc:$('punc').checked,ddc:$('ddc').checked,autoFollowCodex:$('autoFollowCodex').checked};
  for(const id of ['appid','token','apikey'])if($(id).value)body[id]=$(id).value;
  $('save').disabled=true;$('saved').textContent='正在保存…';
  try{const r=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const result=await r.json().catch(()=>({message:'HTTP '+r.status}));if(!r.ok)throw Error(result.message||'HTTP '+r.status);config=result;for(const id of ['appid','token','apikey'])$(id).value='';$('saved').textContent='已保存；快捷键和 Codex 任务已立即生效';}
  catch(e){$('saved').textContent='保存失败：'+e.message;}finally{$('save').disabled=false;}
};
async function poll(){try{const r=await fetch('/api/status');const s=await r.json();$('live').textContent=s.modeHotkeyOk===false?'后台在线 · 模式快捷键冲突':'后台在线 · 录音键 '+(s.recordHotkey||'?');$('state').textContent=s.state;$('message').textContent=s.message+(s.modeHotkeyOk===false?' / '+(s.modeHotkey||'模式键')+'：'+s.modeHotkeyError:'');$('target').textContent=s.target?'目标：'+s.target:'';$('lastText').value=s.lastText||'';}catch{$('live').textContent='后台断开';}setTimeout(poll,500);}
load().catch(e=>$('saved').textContent=e.message);poll();
