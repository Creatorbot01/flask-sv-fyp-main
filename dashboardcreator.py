"""CRIntegration Dashboard Creator.  Run: pip install flask && python dashboardcreator.py  ->  http://localhost:5001
Design files are JSON (widgets, plus variables, scripts and tokens from the Logic and Tokens tabs). The GPS map needs internet (Leaflet from cdnjs, tiles from OpenStreetMap)."""
from flask import Flask

app = Flask(__name__)

PAGE = r"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CRIntegration Creator</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
:root{--bg:#e8ecef;--pn:#fff;--ink:#1c2a33;--mut:#6b7c88;--ac:#0f6e8c;--al:#d6452b;--ln:#cfd7dd}
[data-theme=dark]{--bg:#12191e;--pn:#1b252c;--ink:#e6eef2;--mut:#8ea0ac;--ac:#2f95b8;--ln:#2f3d47}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.4 Bahnschrift,"DIN Alternate","Segoe UI",system-ui,sans-serif;display:grid;grid-template-columns:210px 1fr 300px;height:100vh}
aside{background:var(--pn);padding:14px;overflow:auto;border-right:1px solid var(--ln)}aside.r{border:0;border-left:1px solid var(--ln)}
aside .brand{font-size:21px;font-weight:700;letter-spacing:.5px;color:var(--ac)}main{padding:16px;overflow:auto}h3{margin:0 0 10px;font-size:15px}
button,input,select{font:inherit;color:var(--ink)}button{background:var(--ac);color:#fff;border:0;border-radius:4px;padding:7px 10px;cursor:pointer;margin:0 4px 6px 0}
button.g{background:transparent;color:var(--ink);border:1px solid var(--ln)}button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid var(--al);outline-offset:1px}
.pal button{display:block;width:100%;text-align:left}input,select{width:100%;padding:6px;border:1px solid var(--ln);border-radius:4px;margin:2px 0 8px;background:var(--pn)}
input::placeholder{color:var(--mut);opacity:.7}label{font-size:13px;color:var(--mut)}label.c{display:flex;gap:6px;align-items:center}label.c input{width:auto;margin:0}
.top{display:flex;gap:12px}.top div{flex:1}hr{border:0;border-top:1px solid var(--ln);margin:12px 0}
#cv{position:relative;margin-top:8px;border:1px solid var(--ln);background-image:linear-gradient(var(--ln) 1px,transparent 1px),linear-gradient(90deg,var(--ln) 1px,transparent 1px);background-size:20px 20px;background-color:var(--bg)}
.w{position:absolute;background:var(--pn);border:1px solid var(--ln);border-radius:6px;display:flex;flex-direction:column;cursor:move;touch-action:none;user-select:none;overflow:hidden;container-type:size;isolation:isolate;z-index:1}
.w.s{outline:2px solid var(--ac);z-index:2}.hd{padding:4px 4px 0 8px;font-size:13px;color:var(--mut);display:flex;justify-content:space-between;align-items:center}
.hd button{padding:0 6px;margin:0}.bd{flex:1;min-height:0;padding:4px 8px 8px;pointer-events:none;display:flex;flex-direction:column;justify-content:center;position:relative}
.bd.map{padding:0;justify-content:flex-start}.mpw{flex:1;min-height:0;position:relative}.mp{position:absolute;inset:0}.er{position:absolute;inset:0;display:none;align-items:center;justify-content:center;background:rgba(214,69,43,.88);color:#fff;font-weight:600;z-index:1200}.gc{padding:3px 8px;font-size:12px;color:var(--mut);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rz{display:none;position:absolute;right:0;bottom:0;width:18px;height:18px;cursor:nwse-resize;background:linear-gradient(135deg,transparent 50%,var(--ac) 50%);z-index:5}.w.s .rz,.w:hover .rz{display:block}
.tr{height:12px;background:var(--ln);border-radius:6px;overflow:hidden;position:relative;margin:6px 0}.tr i{display:block;height:100%}.tr b{position:absolute;top:0;bottom:0;width:2px;background:var(--ink)}
.row{display:flex;gap:6px}.row input{margin:0;flex:1;min-width:0;height:clamp(32px,30cqh,72px);font-size:clamp(13px,14cqh,26px)}.row button{margin:0;height:clamp(32px,30cqh,72px);font-size:clamp(13px,14cqh,26px)}.big{font-size:clamp(16px,30cqh,72px);word-break:break-word;line-height:1.15}.bd>button{flex:1;width:100%;margin:0;font-size:clamp(14px,22cqh,40px)}.bd img{max-width:100%;max-height:100%}
.gr line,.gr polyline,.gr polygon{vector-effect:non-scaling-stroke}
.gw svg{display:block}
[data-theme=dark] .leaflet-tile{filter:invert(1) hue-rotate(180deg) brightness(.95) contrast(.9)}
.tk{display:grid;grid-template-columns:1fr 1.2fr 2fr auto auto;gap:6px;align-items:center;margin:8px 0 2px}.tk input,.tk select{margin:0}
.tabs{display:flex;gap:6px;margin-bottom:10px}.tabs button{margin:0}
textarea{font:inherit;color:var(--ink);width:100%;padding:6px;border:1px solid var(--ln);border-radius:4px;margin:2px 0 8px;background:var(--pn);resize:vertical}
label.fl{display:block}.mu{color:var(--mut)}code{background:var(--bg);padding:0 3px;border-radius:3px}aside ul{margin:4px 0 8px;padding-left:18px}
.sc{background:var(--pn);border:1px solid var(--ln);border-radius:6px;padding:10px;margin-bottom:12px}
.vr{display:grid;grid-template-columns:1.2fr 1fr 1.2fr auto;gap:6px;align-items:center;margin:6px 0}.vr input,.vr select{margin:0}
.sh{display:grid;grid-template-columns:1.4fr 1.2fr 1.4fr auto;gap:8px;align-items:end}
.bl{background:var(--bg);border:1px solid var(--ln);border-left:4px solid var(--ac);border-radius:4px;padding:6px 8px;margin:6px 0}
.bl[data-t=if],.bl[data-t=repeat]{border-left-color:#d6882b}.bl[data-t=discord]{border-left-color:#5865f2}.bl[data-t=widget]{border-left-color:#0f8f6b}.bl[data-t=call]{border-left-color:#8b5cf6}
.bh{display:flex;gap:4px;align-items:center;font-weight:600;font-size:13px;margin-bottom:4px}.bh .sp{flex:1}.bh button{padding:0 7px;margin:0}
.nest{margin:4px 0 4px 10px;padding-left:8px;border-left:2px dashed var(--ln)}.ef{display:grid;grid-template-columns:1fr 1fr auto auto;gap:6px;align-items:end}
select.addb{width:auto;margin:6px 0 0}
@media(max-width:800px){body{grid-template-columns:1fr;height:auto}.sh,.ef,.tk{grid-template-columns:1fr}}
</style>
<aside><div class="brand">CRIntegration</div><small>Dashboard Creator</small><hr>
<button class="g" id="tg"></button><hr><h3>Add widget</h3><div class="pal" id="pal"></div><hr><h3>Design file (.json)</h3>
<button onclick="dl()">Download design</button><button class="g" onclick="dl(true)">Download without tokens</button><button class="g" onclick="ld.click()">Load design</button><input type="file" id="ld" hidden accept=".json"></aside>
<main><div class="tabs"><button id="tabD" onclick="tab('d')">Design</button><button id="tabL" class="g" onclick="tab('l')">Logic</button><button id="tabT" class="g" onclick="tab('t')">Tokens</button></div>
<div id="pd"><div class="top"><div><label>Dashboard title</label><input id="ttl"></div><div><label>Canvas width in px (600-2400)</label><input id="cw" type="number" min="600" max="2400" step="20"></div></div>
<div id="cv"></div></div><div id="pl" hidden></div><div id="pt" hidden></div><datalist id="hooks"></datalist></main><aside class="r" id="props"></aside>
<script>
const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const th=t=>{document.documentElement.dataset.theme=t;$('tg').textContent=t=='dark'?'Light mode':'Dark mode';try{localStorage.setItem('crintegration-theme',t)}catch(e){}};
let saved;try{saved=localStorage.getItem('crintegration-theme')}catch(e){}th(saved||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'));
$('tg').onclick=()=>th(document.documentElement.dataset.theme=='dark'?'light':'dark');
const T={
 text:{n:'Text',w:200,h:100,ph:'--',f:[]},
 bar:{n:'Bar',w:260,h:100,ph:'50',f:[['max','Max value','number']],d:{max:100}},
 meter:{n:'Meter',w:260,h:110,ph:'50',f:[['max','Max value','number'],['limit','Limit (color changes above)','number'],['color','Normal color','color'],['alertColor','Exceeded color','color'],['showPercent','Show as percentage','bool']],d:{max:100,limit:80,color:'#0f8f6b',alertColor:'#d6452b',showPercent:true}},
 image:{n:'Image',w:240,h:180,ph:'',f:[]},
 button:{n:'Button',w:160,h:90,f:[['labelMode','Show label','select',[['both','Top and inside button'],['top','Top only'],['inside','Inside button only']]],['value','Value sent when pressed','text'],['idleValue','Value sent when not pressed','text'],['oneshot','Send pressed value once (off = toggle, press again to return to idle)','bool'],['color','Button color','color'],['pressColor','Color when pressed or toggled on','color'],['pressMs','Pressed color duration (ms, send once mode)','number']],d:{labelMode:'both',value:'1',idleValue:'0',oneshot:true,color:'#0f6e8c',pressColor:'#0f8f6b',pressMs:400}},
 slider:{n:'Scroll bar',w:280,h:110,f:[['start','Start','number'],['limit','Limit','number']],d:{start:0,limit:100}},
 input:{n:'Text input',w:290,h:110,ph:'Type here',f:[['mode','Send mode','select',[['button','Send with button'],['auto','Auto send after pause']]],['delay','Auto send delay (seconds)','number'],['sendLabel','Button label','text']],d:{mode:'button',delay:2.5,sendLabel:'Send'}},
 graph:{n:'Graph',w:360,h:220,ph:'20,35,30,50,45,60,55',f:[['points','Points shown','number'],['color','Line color','color'],['yMin','Y axis min (blank = auto)','text'],['yMax','Y axis max (blank = auto)','text']],d:{points:50,color:'#0f6e8c',yMin:'',yMax:''}},
 gps:{n:'GPS coordinate',w:340,h:260,ph:'3.1390,101.6869',f:[['zoom','Map zoom (1-19)','number']],d:{zoom:15}}};
const NOPH=['button','slider'],S=v=>Math.round(v/10)*10;
const MIN={text:[120,60],bar:[160,70],meter:[180,80],image:[100,80],button:[100,50],slider:[180,80],input:[200,80],graph:[240,160],gps:[200,160]};
let D={title:'My Dashboard',width:1200,widgets:[],variables:[],scripts:[],tokens:[]},sel=null,els={},maps={};
$('pal').innerHTML=Object.entries(T).map(([k,v])=>`<button onclick="add('${k}')">+ ${v.n}</button>`).join('');
function niceStep(r,n){const raw=r/n,e=Math.pow(10,Math.floor(Math.log10(raw))),f=raw/e;return(f<=1?1:f<=2?2:f<=5?5:10)*e}
function graphSVG(pts,w,W,H){
 const pl=40,pr=12,pt=8,pb=20,pw=W-pl-pr,ph=H-pt-pb,ok=x=>String(x??'').trim()!==''&&isFinite(+x),fx=n=>+n.toFixed(2);
 if(pw<40||ph<30||!pts.length)return'';
 const vs=pts.map(q=>q[1]);let lo=ok(w.yMin)?+w.yMin:Math.min(...vs),hi=ok(w.yMax)?+w.yMax:Math.max(...vs);
 if(!(hi>lo)){if(ok(w.yMin)||ok(w.yMax))hi=lo+1;else{lo-=1;hi+=1}}
 const sy=niceStep(hi-lo,Math.max(2,Math.min(6,Math.floor(ph/34))));
 if(!ok(w.yMin))lo=Math.floor(lo/sy+1e-9)*sy;if(!ok(w.yMax))hi=Math.ceil(hi/sy-1e-9)*sy;
 const Y=v=>pt+ph-(Math.min(hi,Math.max(lo,v))-lo)/(hi-lo)*ph,tx='style="fill:var(--mut);font-size:10px"',gl='style="stroke:var(--ln)"';let g='';
 for(let i=Math.ceil(lo/sy-1e-9);i*sy<=hi+1e-9;i++){const v=i*sy,y=Y(v);g+=`<line x1="${pl}" x2="${pl+pw}" y1="${fx(y)}" y2="${fx(y)}" ${gl}/><text x="${pl-5}" y="${fx(y+3.5)}" text-anchor="end" ${tx}>${fx(v)}</text>`}
 const t1=pts[pts.length-1][0],T=Math.max(1,t1-pts[0][0]),sx=niceStep(T,Math.max(2,Math.min(8,Math.floor(pw/70))));
 for(let i=0;i*sx<=T+1e-9;i++){const a=i*sx,x=pl+pw-a/T*pw,lab=i==0?'now':sx>=60?`-${fx(a/60)}m`:`-${fx(a)}s`;
  g+=`<line x1="${fx(x)}" x2="${fx(x)}" y1="${pt}" y2="${pt+ph}" ${gl}/><text x="${fx(x)}" y="${H-5}" text-anchor="${i==0?'end':'middle'}" ${tx}>${lab}</text>`}
 const c=w.color||'#0f6e8c',xy=pts.map(q=>[pl+pw-(t1-q[0])/T*pw,Y(q[1])]),line=xy.map(q=>q.map(fx).join(',')).join(' '),l=xy[xy.length-1];
 return`<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${g}<polygon fill="${c}" fill-opacity=".15" points="${fx(xy[0][0])},${pt+ph} ${line} ${fx(l[0])},${pt+ph}"/><polyline fill="none" stroke="${c}" stroke-width="2" stroke-linejoin="round" points="${line}"/><circle cx="${fx(l[0])}" cy="${fx(l[1])}" r="3.5" fill="${c}"/></svg>`}
function geo(v){let p=v;if(typeof v=='string')p=v.split(',').map(s=>s.trim()===''?NaN:+s);else if(v&&typeof v=='object'&&!Array.isArray(v))p=[v.lat??v.latitude,v.lng??v.lon??v.longitude];
 return Array.isArray(p)&&p.length==2&&p.every(n=>typeof n=='number'&&isFinite(n))&&Math.abs(p[0])<=90&&Math.abs(p[1])<=180?p:null}
function add(t){let n=1;while(D.widgets.some(w=>w.name==t+n))n++;const k=D.widgets.length%10*20;
 const w={id:'w'+Date.now(),type:t,name:t+n,label:T[t].n,placeholder:T[t].ph??'',x:20+k,y:20+k,w:T[t].w,h:T[t].h,...JSON.parse(JSON.stringify(T[t].d||{}))};
 D.widgets.push(w);mkBox(w);select(w.id);fit()}
function fit(){const c=$('cv');c.style.width=D.width+'px';c.style.height=Math.max(500,...D.widgets.map(w=>w.y+w.h+200))+'px'}
function place(w,b){b.style.cssText=`left:${w.x}px;top:${w.y}px;width:${w.w}px;height:${w.h}px`}
function pv(w){const v=w.placeholder,mx=+w.max||100,p=Math.min(100,Math.max(0,(+v||0)/mx*100)),ok=x=>String(x??'').trim()!=='';
 if(w.type=='bar')return`<div class=tr><i style="width:${p}%;background:var(--ac)"></i></div>${esc(v)} / ${mx}`;
 if(w.type=='meter'){const o=+v>+w.limit,pc=w.showPercent!==false;return`<div class=tr><i style="width:${p}%;background:${o?w.alertColor:w.color}"></i><b style="left:${Math.min(100,w.limit/mx*100)}%"></b></div>${pc?p.toFixed(0)+'% (limit '+(w.limit/mx*100).toFixed(0)+'%)':esc(v)+' (limit '+w.limit+')'}`}
 if(w.type=='image')return/^(https?:|data:)/.test(v)?`<img src="${esc(v)}">`:'<small>image URL or base64 shows here</small>';
 if(w.type=='button')return`<button style="background:${w.color}">${w.labelMode=='top'?'':esc(w.label)}</button>`;
 if(w.type=='slider')return`<input type=range min=${w.start} max=${w.limit} value=${w.start}><small>${w.start} to ${w.limit}</small>`;
 if(w.type=='input')return`<div class=row><input placeholder="${esc(v)}">${w.mode=='button'?`<button>${esc(w.sendLabel)}</button>`:''}</div>${w.mode=='auto'?`<small>auto sends after ${w.delay}s idle</small>`:''}`;
 return`<div class=big>${esc(v)}</div>`}
function refresh(w){const r=els[w.id];if(!r)return;r.hd.textContent=w.type=='button'&&w.labelMode=='inside'?'':w.label;
 if(w.type=='graph'){if(!r.bd.querySelector('.gw')){r.bd.innerHTML='<div class="big gv" style="font-size:20px"></div><div class=gw style="flex:1;min-height:0;position:relative;overflow:hidden"></div>';new ResizeObserver(()=>refresh(w)).observe(r.box)}
  const h=String(w.placeholder??'').split(',').map(q=>q.trim()).filter(Boolean).map(Number).filter(isFinite).map((v,i)=>[i*10,v]),gw=r.bd.querySelector('.gw');
  r.bd.querySelector('.gv').textContent=h.length?h[h.length-1][1]:'--';gw.innerHTML=h.length?graphSVG(h,w,gw.clientWidth,gw.clientHeight):'<small>Placeholder: comma separated numbers, for example 20,35,30,50</small>';return}
 if(w.type!='gps'){r.bd.innerHTML=pv(w);return}
 if(typeof L=='undefined'){r.bd.innerHTML='<small>Map needs internet (Leaflet)</small>';return}
 if(!maps[w.id]){r.bd.className='bd map';r.bd.innerHTML='<div class=mpw><div class=mp></div><div class=er>Error: invalid data</div></div><div class=gc></div>';
  const m=L.map(r.bd.querySelector('.mp'),{zoomControl:false,dragging:false,scrollWheelZoom:false,doubleClickZoom:false,boxZoom:false,keyboard:false,touchZoom:false});
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap'}).addTo(m);
  maps[w.id]={m,k:L.marker([0,0]).addTo(m)};new ResizeObserver(()=>m.invalidateSize()).observe(r.box)}
 const g=maps[w.id],p=geo(w.placeholder);r.bd.querySelector('.er').style.display=p?'none':'flex';r.bd.querySelector('.gc').textContent=p?`${p[0].toFixed(5)}, ${p[1].toFixed(5)}`:'Invalid coordinate';
 if(p){g.k.setLatLng(p);g.m.setView(p,+w.zoom||15)}else g.m.setView([20,0],2)}
function mkBox(w){const b=document.createElement('div');b.className='w';place(w,b);
 b.innerHTML='<div class=hd><span></span><button class=g title="Delete widget">&#10005;</button></div><div class=bd></div><i class=rz></i>';$('cv').appendChild(b);
 els[w.id]={box:b,hd:b.querySelector('.hd span'),bd:b.querySelector('.bd')};refresh(w);
 b.querySelector('button').onclick=e=>{e.stopPropagation();rm(w.id)};
 b.onpointerdown=e=>{if(e.target.closest('button'))return;select(w.id);const rz=e.target.classList.contains('rz'),sx=e.clientX,sy=e.clientY,ox=w.x,oy=w.y,ow=w.w,oh=w.h;b.setPointerCapture(e.pointerId);
  b.onpointermove=ev=>{const dx=ev.clientX-sx,dy=ev.clientY-sy;
   if(rz){const mn=MIN[w.type]||[100,60];w.w=Math.min(D.width-w.x,Math.max(mn[0],S(ow+dx)));w.h=Math.max(mn[1],S(oh+dy))}else{w.x=Math.min(D.width-w.w,Math.max(0,S(ox+dx)));w.y=Math.max(0,S(oy+dy))}place(w,b)};
  b.onpointerup=()=>{b.onpointermove=b.onpointerup=null;fit();props()}}}
function rm(id){const i=D.widgets.findIndex(w=>w.id==id);D.widgets.splice(i,1);els[id].box.remove();delete els[id];if(maps[id]){maps[id].m.remove();delete maps[id]}if(sel==id)sel=null;props();fit()}
function select(id){sel=id;Object.entries(els).forEach(([k,r])=>r.box.classList.toggle('s',k==id));props()}
function props(){const w=D.widgets.find(x=>x.id==sel),P=$('props');if(!w){P.innerHTML='<h3>Properties</h3><small>Select a widget to edit it. Drag to move, pull the bottom right corner to resize.</small>';return}
 const row=(k,l,t,o)=>t=='bool'?`<label class=c><input type=checkbox ${w[k]?'checked':''} onchange="up('${k}',this.checked)">${l}</label>`
  :t=='select'?`<label>${l}</label><select onchange="up('${k}',this.value)">${o.map(([v,n])=>`<option value="${v}" ${w[k]==v?'selected':''}>${n}</option>`).join('')}</select>`
  :`<label>${l}</label><input type=${t} value="${esc(w[k])}" oninput="up('${k}',this.type=='number'?+this.value:this.value)">`;
 P.innerHTML=`<h3>${T[w.type].n} properties</h3>`+row('label','Display label','text')+row('name','Name (JSON payload key)','text')+(NOPH.includes(w.type)?'':row('placeholder',w.type=='graph'?'Placeholder values (comma separated numbers)':'Placeholder value','text'))+'<hr>'+T[w.type].f.map(f=>row(...f)).join('')+`<hr><small>Position ${w.x}, ${w.y} and size ${w.w} x ${w.h} (minimum ${(MIN[w.type]||[100,60]).join(' x ')})</small>`}
function up(k,v){const w=D.widgets.find(x=>x.id==sel);w[k]=v;refresh(w)}
function build(){Object.values(maps).forEach(g=>g.m.remove());maps={};els={};$('cv').innerHTML='';D.widgets.forEach(mkBox);sel=null;$('ttl').value=D.title;$('cw').value=D.width;fit();props();if(TAB!='d')tab(TAB);syncHooks()}
$('ttl').oninput=e=>D.title=e.target.value;$('cw').onchange=e=>{D.width=Math.max(600,Math.min(2400,+e.target.value||1200));e.target.value=D.width;fit()};
function dl(bare){const pr=checkLogic();if(pr.length&&!confirm('Logic problems:\n- '+pr.join('\n- ')+'\n\nDownload anyway?'))return;const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(bare?{...D,tokens:D.tokens.map(t=>({...t,value:''}))}:D,null,2)],{type:'application/json'}));a.download=(D.title||'dashboard').replace(/\W+/g,'_')+'.json';a.click()}
$('ld').onchange=async e=>{try{const j=JSON.parse(await e.target.files[0].text());if(!Array.isArray(j.widgets))throw 0;
 j.width=j.width||1200;j.variables=Array.isArray(j.variables)?j.variables:[];j.scripts=Array.isArray(j.scripts)?j.scripts:[];j.tokens=Array.isArray(j.tokens)?j.tokens:[];j.widgets.forEach((w,i)=>{w.id=w.id||'w'+i+Date.now();w.x??=20;w.y??=20+i*120;w.w??=260;w.h??=100;const mn=MIN[w.type]||[100,60];w.w=Math.max(w.w,mn[0]);w.h=Math.max(w.h,mn[1])});D=j;build()}catch(x){alert('Could not read that file. Load a .json design file made by this creator.')}e.target.value=''};
/* ---------- Logic tab: variables, scripts made of blocks, Discord webhook, functions ---------- */
const RES=['data','param','controls','deviceID','deviceName','true','false','none','i'],IDRE=/^[A-Za-z_]\w*$/;
const WP=[['value','Displayed value'],['label','Label'],['visible','Visible (true or false)'],['color','Color (bar, meter, button, graph)'],['max','Max (bar, meter)'],['limit','Limit (meter)']];
const TRG=[['data','Data is received from the device'],['control','A button, slider or input is used on the website'],['function','Function (started by POST /api/function)']];
const BT={
 set:{n:'Set variable',f:[['var','Variable','var'],['value','To (plain text, or {maths})','text',null,'{temp * 2}']],d:{var:'',value:''}},
 change:{n:'Change variable by',f:[['var','Variable','var'],['value','By','text',null,'1']],d:{var:'',value:'1'}},
 if:{n:'If / else',kids:['then','else'],f:[['cond','Condition','text',null,'data.temp > 30 and alarm == 0']],d:{cond:'',then:[],else:[]}},
 repeat:{n:'Repeat',kids:['body'],f:[['times','Times (max 100, {i} is the round number)','text']],d:{times:'3',body:[]}},
 widget:{n:'Set website widget',f:[['widget','Widget','widget'],['prop','Property','select',WP],['value','To (blank puts it back to normal)','text',null,'Hot: {data.temp}']],d:{widget:'',prop:'value',value:''}},
 discord:{n:'Send Discord webhook',f:[['url','Webhook (token name or URL)','hook',null,'webhook1'],['username','Bot name (optional)','text'],['avatar','Avatar image URL (optional)','text'],['content','Message text','area',null,'Temperature is {data.temp}']],d:{url:'',username:'',avatar:'',content:'',embed:{enabled:false,color:'#5865f2',fields:[]}}},
 call:{n:'Run function',f:[['fn','Function','fn',null,null,1]],d:{fn:'',args:{}}},
 log:{n:'Log message (shown under the Logic button)',f:[['value','Message','text']],d:{value:''}}};
const el=(t,a,...k)=>{const e=document.createElement(t);for(const[x,v]of Object.entries(a||{})){if(x.startsWith('on'))e[x]=v;else if(x=='cls')e.className=v;else if(v!==false&&v!=null)e.setAttribute(x,v===true?'':v)}k.flat(9).forEach(c=>{if(c!=null)e.append(c)});return e};
const vnames=()=>D.variables.map(v=>v.name),wnames=()=>D.widgets.map(w=>w.name),fnames=()=>D.scripts.filter(s=>s.trigger=='function').map(s=>s.name);
const optsOf=(list,cur)=>[['','(choose)'],...list.map(n=>[n,n]),...(cur&&!list.includes(cur)?[[cur,cur+' (missing)']]:[])];
const DYN={var:vnames,widget:wnames,fn:fnames};
function fld(o,k,label,type,opts,ph,after){
 if(DYN[type]){const l=DYN[type];opts=cur=>optsOf(l(),cur);type='select'}
 let c;
 if(type=='bool')c=el('input',{type:'checkbox',checked:!!o[k],onchange:e=>{o[k]=e.target.checked;after&&after()}});
 else if(type=='select')c=el('select',{onchange:e=>{o[k]=e.target.value;after&&after()}},(typeof opts=='function'?opts(o[k]):opts).map(([v,n])=>el('option',{value:v,selected:o[k]==v},n)));
 else if(type=='area')c=el('textarea',{rows:3,placeholder:ph,oninput:e=>o[k]=e.target.value},o[k]??'');
 else c=el('input',{type:type=='color'?'color':'text',value:o[k]||(type=='color'?'#5865f2':''),placeholder:ph,list:type=='hook'?'hooks':null,oninput:e=>o[k]=e.target.value});
 return el('label',{cls:type=='bool'?'c':'fl'},type=='bool'?[c,label]:[label,c])}
const redo=()=>renderLogic();
const newBlock=t=>JSON.parse(JSON.stringify({t,...BT[t].d}));
function walk(list,fn){(list||[]).forEach(b=>{fn(b);['then','else','body'].forEach(k=>b[k]&&walk(b[k],fn))})}
function mv(l,i,d){const j=i+d;if(j<0||j>=l.length)return;[l[i],l[j]]=[l[j],l[i]];redo()}
function blocks(list){const box=el('div');list.forEach((b,i)=>box.append(blockEl(b,list,i)));
 box.append(el('select',{cls:'addb',onchange:e=>{if(e.target.value){list.push(newBlock(e.target.value));redo()}}},el('option',{value:''},'+ Add block...'),Object.entries(BT).map(([k,v])=>el('option',{value:k},v.n))));return box}
function blockEl(b,list,i){const d=BT[b.t];if(!d)return el('div',{cls:'bl'},'Unknown block '+b.t);
 const f=el('div'),hd=el('div',{cls:'bh'},d.n,el('span',{cls:'sp'}),
  el('button',{cls:'g',title:'Move up',onclick:()=>mv(list,i,-1)},'\u2191'),el('button',{cls:'g',title:'Move down',onclick:()=>mv(list,i,1)},'\u2193'),
  el('button',{cls:'g',title:'Delete block',onclick:()=>{list.splice(i,1);redo()}},'\u2715'));
 (d.f||[]).forEach(([k,l,t,o,ph,re])=>f.append(fld(b,k,l,t,o,ph,re?redo:null)));
 if(b.t=='call')callUI(b,f);if(b.t=='discord')discordUI(b,f);
 (d.kids||[]).forEach(k=>{b[k]??=[];f.append(el('div',{cls:'nest'},el('small',{cls:'mu'},{then:'Then',else:'Else',body:'Do'}[k]),blocks(b[k])))});
 return el('div',{cls:'bl','data-t':b.t},hd,f)}
function callUI(b,f){const s=D.scripts.find(x=>x.trigger=='function'&&x.name==b.fn);
 f.append(el('label',{cls:'fl'},'Parameters, one per line as name=value',el('textarea',{rows:2,placeholder:'level=3',oninput:e=>{b.args={};e.target.value.split('\n').forEach(l=>{const m=l.indexOf('=');if(m>0)b.args[l.slice(0,m).trim()]=l.slice(m+1)})}},Object.entries(b.args||{}).map(([k,v])=>k+'='+v).join('\n'))),
  s&&(s.params||[]).length?el('small',{cls:'mu'},'This function takes: '+s.params.join(', ')):null)}
function discordUI(b,f){const e=b.embed??={enabled:false,color:'#5865f2',fields:[]};e.fields??=[];e.color??='#5865f2';
 f.append(el('small',{cls:'mu'},'Pick a Discord token name from the Tokens tab (or a name set in config.json). A full URL typed here is saved in the design file as plain text.'),fld(e,'enabled','Add an embed','bool',null,null,redo));
 if(e.enabled){const x=el('div',{cls:'nest'});
  [['title','Embed title','text'],['description','Embed description','area'],['color','Embed color','color'],['url','Title link URL','text'],['author','Author name','text'],['footer','Footer text','text'],['thumbnail','Thumbnail image URL','text'],['image','Large image URL','text']].forEach(([k,l,t])=>x.append(fld(e,k,l,t)));
  x.append(fld(e,'timestamp','Show the current time on the embed','bool'));
  e.fields.forEach((q,j)=>x.append(el('div',{cls:'ef'},fld(q,'name','Field name','text'),fld(q,'value','Field value','text'),fld(q,'inline','Inline','bool'),el('button',{cls:'g',title:'Remove field',onclick:()=>{e.fields.splice(j,1);redo()}},'\u2715'))));
  if(e.fields.length<25)x.append(el('button',{cls:'g',onclick:()=>{e.fields.push({name:'',value:'',inline:false});redo()}},'+ Add embed field'));f.append(x)}}
function renameVar(v,n){n=n.trim();if(!IDRE.test(n)||RES.includes(n)||vnames().includes(n)){alert('Variable names use letters, digits and _, cannot start with a digit, cannot repeat, and cannot be one of: '+RES.join(', '));return redo()}
 const old=v.name;D.scripts.forEach(s=>walk(s.blocks,b=>{if(b.var===old)b.var=n}));v.name=n;redo()}
function varsUI(){const box=el('div',{cls:'sc'},el('h3',null,'Variables'),el('small',{cls:'mu'},'Shared variables can be read and written by the device and the website. Website only variables stay on the dashboard server. Use a variable name inside {braces} anywhere in a block.'));
 D.variables.forEach((v,i)=>box.append(el('div',{cls:'vr'},
  el('input',{value:v.name,placeholder:'name',title:'Variable name',onchange:e=>renameVar(v,e.target.value)}),
  el('select',{onchange:e=>v.scope=e.target.value},[['shared','Shared (device + website)'],['local','Website only']].map(([a,b])=>el('option',{value:a,selected:v.scope==a},b))),
  el('input',{value:v.initial??'',placeholder:'start value',oninput:e=>v.initial=e.target.value}),
  el('button',{cls:'g',title:'Delete variable',onclick:()=>{D.variables.splice(i,1);redo()}},'\u2715'))));
 box.append(el('button',{onclick:()=>{let n=1;while(D.variables.some(v=>v.name=='var'+n))n++;D.variables.push({name:'var'+n,scope:'shared',initial:'0'});redo()}},'+ Add variable'));return box}
function addScript(tr){let n=1;const nm=()=>tr=='function'?'myFunction'+n:'Script '+n;while(D.scripts.some(s=>s.name==nm()))n++;D.scripts.push({name:nm(),trigger:tr,params:[],blocks:[]});redo()}
function scriptsUI(){const box=el('div');
 D.scripts.forEach((s,i)=>{const fn=s.trigger=='function',ex=JSON.stringify({function:s.name,params:Object.fromEntries((s.params||[]).map(p=>[p,'...']))});
  box.append(el('div',{cls:'sc'},
   el('div',{cls:'sh'},fld(s,'name',fn?'Function name':'Script name','text'),fld(s,'trigger','Runs when','select',TRG,null,redo),
    fn?el('label',{cls:'fl'},'Parameters (comma separated)',el('input',{value:(s.params||[]).join(', '),oninput:e=>s.params=e.target.value.split(',').map(x=>x.trim()).filter(Boolean)})):el('span'),
    el('button',{cls:'g',title:'Delete script',onclick:()=>{if(confirm('Delete "'+s.name+'"?')){D.scripts.splice(i,1);redo()}}},'\u2715')),
   fn?el('small',{cls:'mu'},'Start it with POST /api/function/<deviceID> and body '+ex+'. Inside the blocks use {param.name}.'):el('small',{cls:'mu'},s.trigger=='data'?'Runs on every POST /api/data. Use {data.key} for the posted values.':'Runs when a website control changes. {param.name} is the widget name and {param.value} the value sent.'),
   blocks(s.blocks)))});
 box.append(el('button',{onclick:()=>addScript('data')},'+ Add script'),el('button',{cls:'g',onclick:()=>addScript('function')},'+ Add function'));return box}
function renderLogic(){syncHooks();$('pl').replaceChildren(varsUI(),el('h3',null,'Scripts and functions'),scriptsUI())}
function help(){$('props').innerHTML=`<h3>Logic help</h3><small><b>Plain text</b> is sent as typed. Put maths or a value in <b>{braces}</b>, for example <code>Temp is {data.temp}C</code> or <code>{count + 1}</code>. A field with only one {expression} keeps its type.<hr>
<b>Names you can use</b><ul><li>your variables, like <code>count</code></li><li><code>data.key</code> latest posted value (<code>data["my-key"]</code> for odd names)</li><li><code>param.name</code> function or control values</li><li><code>controls.slider1</code> current website input</li><li><code>deviceID</code>, <code>deviceName</code></li><li><code>i</code> inside Repeat</li></ul>
<b>Conditions</b> need no braces: <code>data.temp &gt; 30 and not alarm</code><ul><li><code>+ - * / % </code></li><li><code>== != &lt; &gt; &lt;= &gt;=</code></li><li><code>and or not in</code></li></ul>
<b>Functions</b><ul><li><code>round(x,n) abs min max</code></li><li><code>num(x,default) int str len</code></li><li><code>upper lower contains(a,b)</code></li><li><code>split(text,sep) isnum(x)</code></li><li><code>now() clock()</code></li></ul>
Numbers typed as text are treated as numbers, and text comparisons ignore case. Scripts run on the dashboard server, so they work with no browser open.</small>`}
let TAB='d';
function tab(x){TAB=x;[['d','pd','tabD'],['l','pl','tabL'],['t','pt','tabT']].forEach(([k,pn,bt])=>{$(pn).hidden=k!=x;$(bt).className=k==x?'':'g'});if(x=='l'){renderLogic();help()}else if(x=='t'){renderTokens();helpTok()}else props()}
function checkLogic(){const p=[],vs=vnames(),fs=fnames(),ws=wnames();
 vs.forEach((n,i)=>{if(!IDRE.test(n)||RES.includes(n))p.push(`Variable "${n}" has an invalid or reserved name`);if(vs.indexOf(n)!=i)p.push(`Variable "${n}" is defined twice`)});
 fs.forEach((n,i)=>{if(!IDRE.test(n))p.push(`Function name "${n}" must use letters, digits and _ only`);if(fs.indexOf(n)!=i)p.push(`Function "${n}" is defined twice`)});
 D.scripts.forEach(s=>{(s.params||[]).forEach(a=>{if(!IDRE.test(a))p.push(`"${s.name}": invalid parameter name "${a}"`)});
  walk(s.blocks,b=>{if((b.t=='set'||b.t=='change')&&!vs.includes(b.var))p.push(`"${s.name}": variable "${b.var||'(none)'}" is not defined`);
   if(b.t=='widget'&&!ws.includes(b.widget))p.push(`"${s.name}": widget "${b.widget||'(none)'}" is not in the design`);
   if(b.t=='discord'){const u=(b.url||'').trim();if(!u)p.push(`"${s.name}": a Discord block has no webhook`);else if(!/^https?:/.test(u)&&!u.includes('{')&&!D.tokens.some(t=>t.kind=='discord'&&t.name==u&&t.value))p.push(`"${s.name}": webhook "${u}" is not a Discord token with a value (fine only if config.json defines it)`)}
   if(b.t=='call'&&!fs.includes(b.fn))p.push(`"${s.name}": function "${b.fn||'(none)'}" does not exist`)})});
 D.tokens.forEach((t,i)=>{if(!IDRE.test(t.name))p.push(`Token name "${t.name}" must use letters, digits and _ only`);if(D.tokens.findIndex(x=>x.name==t.name)!=i)p.push(`Token "${t.name}" is defined twice`);if(t.kind=='discord'&&t.value&&!DISCORD_RE.test(t.value))p.push(`Token "${t.name}" is not a valid Discord webhook URL`)});
 return p}

/* ---------- Tokens tab: secrets stored in the design file, never sent to the website ---------- */
const TK=[['discord','Discord webhook URL'],['function','Function endpoint token']];
const DISCORD_RE=/^https:\/\/(?:(?:canary|ptb)\.)?(?:discord|discordapp)\.com\/api(?:\/v\d+)?\/webhooks\/\d+\/[\w-]+\/?$/;
function syncHooks(){$('hooks').replaceChildren(...D.tokens.filter(t=>t.kind=='discord'&&t.name).map(t=>el('option',{value:t.name})))}
function tokenUse(n){let c=0;D.scripts.forEach(s=>walk(s.blocks,b=>{if(b.t=='discord'&&(b.url||'').trim()===n)c++}));return c}
function tokenNote(t){if(!t.value)return'No value yet';if(t.kind=='discord')return DISCORD_RE.test(t.value)?'Used by '+tokenUse(t.name)+' Discord block(s)':'Not a valid Discord webhook URL';return'Devices send it as header X-Token (or "token" in the body) with POST /api/function'}
function renameTok(t,n){n=n.trim();if(!IDRE.test(n)||D.tokens.some(x=>x!==t&&x.name==n)){alert('Token names use letters, digits and _, cannot start with a digit, and cannot repeat.');return renderTokens()}
 const old=t.name;D.scripts.forEach(s=>walk(s.blocks,b=>{if(b.t=='discord'&&(b.url||'').trim()===old)b.url=n}));t.name=n;renderTokens()}
function addToken(kind){let n=1;const base=kind=='discord'?'webhook':'functionKey';while(D.tokens.some(t=>t.name==base+n))n++;
 const v=kind=='function'?[...crypto.getRandomValues(new Uint8Array(16))].map(b=>b.toString(16).padStart(2,'0')).join(''):'';
 D.tokens.push({name:base+n,kind,value:v});renderTokens()}
function renderTokens(){syncHooks();
 const box=el('div',{cls:'sc'},el('h3',null,'Tokens'),el('small',{cls:'mu'},'Tokens are saved inside the design file next to the widgets. The hoster keeps them on the server and never sends them to the website. Use "Download without tokens" in the left panel when you share a design.'));
 D.tokens.forEach((t,i)=>{const note=el('small',{cls:'mu'},tokenNote(t)),inp=el('input',{type:'password',value:t.value||'',placeholder:t.kind=='discord'?'https://discord.com/api/webhooks/...':'secret',autocomplete:'off',oninput:e=>{t.value=e.target.value.trim();note.textContent=tokenNote(t)}});
  box.append(el('div',{cls:'tk'},
   el('input',{value:t.name,placeholder:'name',title:'Token name, used by blocks',onchange:e=>renameTok(t,e.target.value)}),
   el('select',{onchange:e=>{t.kind=e.target.value;renderTokens()}},TK.map(([v,n])=>el('option',{value:v,selected:t.kind==v},n))),
   inp,el('button',{cls:'g',title:'Show or hide the value',onclick:()=>{inp.type=inp.type=='password'?'text':'password'}},'Show'),
   el('button',{cls:'g',title:'Delete token',onclick:()=>{const u=t.kind=='discord'?tokenUse(t.name):0;if(!u||confirm(`"${t.name}" is used by ${u} Discord block(s). Delete anyway?`)){D.tokens.splice(i,1);renderTokens()}}},'\u2715')),note)});
 if(!D.tokens.length)box.append(el('p',{cls:'mu'},'No tokens yet.'));
 box.append(el('button',{onclick:()=>addToken('discord')},'+ Add Discord webhook'),el('button',{cls:'g',onclick:()=>addToken('function')},'+ Add function token (random)'));
 $('pt').replaceChildren(box)}
function helpTok(){$('props').innerHTML=`<h3>Tokens help</h3><small><b>Discord webhook:</b> paste the webhook URL once, then pick its name in any Discord block. Renaming a token updates the blocks that use it.<hr>
<b>Function token:</b> when the design has at least one, <code>POST /api/function</code> must send it as header <code>X-Token</code> or <code>"token"</code> in the body. Any one of them is accepted, which lets you give each device its own.<hr>
Both kinds live in the design file. The hoster never sends tokens to the browser, but the downloaded file contains them, so keep it private.</small>`}

build();
</script></html>"""


@app.route("/")
def index():
    return PAGE


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
