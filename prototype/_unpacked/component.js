
class Component extends DCLogic {
  state = { sel: 'hunyin', tab: 'overview', added: [], uploadOpen: false, uploads: [], dlOpen: false };

  // ---- palette helpers ----
  gC(g){ return ({S:'#ffd166',A:'#3fb950',B:'#58a6ff',C:'#d29922',D:'#f0883e',Q:'#6e7681'})[g]||'#6e7681'; }
  humanColor(h){ if(h==null) return '#5c6672'; if(h>=75) return '#3fb950'; if(h>=68) return '#d6c24a'; if(h>=60) return '#d29922'; return '#f0883e'; }

  STAGES(){ return [
    {name:'Ingest', cn:'清洗', sub:'去脏·拼接', model:'flash'},
    {name:'Extract', cn:'DNA', sub:'脊柱·钩子', model:'pro'},
    {name:'Plan', cn:'规划', sub:'outline60', model:'pro'},
    {name:'Draft', cn:'草稿', sub:'场景·提纯', model:'flash'},
    {name:'Evaluate', cn:'闸门', sub:'对照 PK', model:'pro·flash'},
    {name:'Assemble', cn:'拼装', sub:'验收报告', model:'—'},
  ]; }

  // ---- per-book stage state array ----
  states(b){
    const n=6, arr=[];
    for(let i=0;i<n;i++){
      let s;
      if(b.status==='certified'){ s='done'; }
      else if(b.status==='running'){ s = i<b.stage?'done' : (i===b.stage?'active':'pending'); }
      else { /* rejected */ s = i<b.stage?'done' : (i===b.stage?'fail':'pending'); }
      arr.push(s);
    }
    return arr;
  }

  BOOKS(){ return [
    {id:'hunyin', title:'隐婚·偏偏宠我', src:'霸总隐婚之偏偏宠我', slug:'霸总隐婚_隐婚偏偏宠我_20260601', genre:'现代言情', grade:'A', comp:'高', stage:5, status:'certified', mode:1, human:75, cost:31},
    {id:'tuihun', title:'退婚·首富千金', src:'重生之首富归来', slug:'首富归来_退婚首富千金_20260603', genre:'都市爽文', grade:'B', comp:'高', stage:5, status:'certified', mode:2, human:76, cost:38},
    {id:'zhaidou', title:'宅斗·庶女谋嫁', src:'庶女当自强', slug:'庶女当自强_宅斗庶女谋嫁_20260605', genre:'古代言情', grade:'A', comp:'中', stage:5, status:'certified', mode:1, human:68, cost:34},
    {id:'chuanyue', title:'重生·穿回那年', src:'重回十八岁', slug:'重回十八岁_重生穿回那年_20260612', genre:'穿越重生', grade:'C', comp:'中', stage:3, status:'running', mode:2, human:63, cost:22},
    {id:'aoshi', title:'傲世·苍穹诀', src:'苍穹至尊诀', slug:'苍穹至尊_傲世苍穹诀_20260608', genre:'玄幻', grade:'S', comp:'低', stage:4, status:'rejected', mode:3, human:54, cost:47},
    {id:'wendao', title:'问道·仙途', src:'凡人问道录', slug:'凡人问道_问道仙途_20260615', genre:'仙侠', grade:'B', comp:'中', stage:1, status:'running', mode:0, human:null, cost:4},
    {id:'xingji', title:'星际·机甲纪元', src:'机甲狂潮', slug:'机甲狂潮_星际机甲纪元_20260614', genre:'科幻', grade:'D', comp:'低', stage:2, status:'running', mode:3, human:null, cost:15},
    {id:'qiandao', title:'签到·从今天暴富', src:'签到系统流', slug:'签到系统_从今天暴富_20260616', genre:'都市系统', grade:'Q', comp:'Q', stage:0, status:'rejected', mode:0, human:null, cost:1},
  ]; }

  MODE(m){ return ({0:'—',1:'模式1 · 保真压缩',2:'模式2 · 强化改写',3:'模式3 · 类型化重构',4:'模式4 · 概念级重启'})[m]||'—'; }
  MODENOTE(m){ return ({0:'未进入质量环',1:'强源主路径 · 只需 +5',2:'补强弱钩子 + 关键章 BoN',3:'按题材范式重排 beat',4:'最高风险 · 仅保概念'})[m]||''; }

  statusInfo(b){
    if(b.status==='certified') return {text:'认证出货', color:'#3fb950', bg:'rgba(63,185,80,.12)'};
    if(b.status==='rejected') return {text:'拒收', color:'#f85149', bg:'rgba(248,81,73,.12)'};
    return {text:'进行中', color:'#58a6ff', bg:'rgba(88,166,255,.12)'};
  }
  certNote(b){
    if(b.status==='certified') return b.human>=75?'出货线 75 达成（当前最佳）':'低空认证 · 承重待补';
    if(b.status==='rejected') return b.grade==='Q'?'Q · form-incompatible 不可压缩':'承重维瓶颈 · 最深仍不过';
    return '质量环进行 · 未终裁';
  }
  stageNote(b){
    const st=this.STAGES()[b.stage];
    if(b.status==='certified') return '全 6 阶段通过 · final.md 已出';
    if(b.status==='rejected') return st.name+' 阶段终止';
    return st.name+' · '+st.sub+' 进行中';
  }

  selectBook(id){ this.setState({sel:id, dlOpen:false}); }
  selectTab(t){ this.setState({tab:t}); }

  // ---- naming: oldname_newname_date ----
  todayStr(){ const d=new Date(); const p=n=>String(n).padStart(2,'0'); return ''+d.getFullYear()+p(d.getMonth()+1)+p(d.getDate()); }
  slugify(s){ return String(s||'').replace(/[\s·.\-\/\\:|，,。、《》<>()（）"'’]+/g,'').trim(); }
  makeSlug(oldn,newn){ return this.slugify(oldn)+'_'+this.slugify(newn)+'_'+this.todayStr(); }

  // ---- batch upload ----
  openUpload(){ this.setState({uploadOpen:true}); }
  closeUpload(){ this.setState({uploadOpen:false, uploads:[]}); }
  triggerFile(){ const el=document.getElementById('hiki-upload-input'); if(el){ el.value=''; el.click(); } }
  onFiles(fileList){
    const arr=Array.from(fileList||[]).filter(f=>/\.txt$/i.test(f.name)||f.type==='text/plain');
    const ups=arr.map((f,i)=>{ const old=f.name.replace(/\.[^.]+$/,''); return {uid:Date.now()+'_'+i+'_'+Math.random().toString(36).slice(2,6), old, nw:old, kb:Math.max(1,Math.round(f.size/1024))}; });
    if(ups.length) this.setState({uploads:[...this.state.uploads, ...ups]});
  }
  setUpName(uid,val){ this.setState({uploads:this.state.uploads.map(u=>u.uid===uid?{...u,nw:val}:u)}); }
  removeUp(uid){ this.setState({uploads:this.state.uploads.filter(u=>u.uid!==uid)}); }
  commitUploads(){
    if(!this.state.uploads.length) return;
    const taken=new Set([...this.BOOKS(), ...this.state.added].map(b=>b.id));
    const added=[];
    this.state.uploads.forEach(u=>{
      const slug=this.makeSlug(u.old, u.nw||u.old);
      let id=slug, k=2; while(taken.has(id)){ id=slug+'_'+k; k++; } taken.add(id);
      added.push({ id, title:(u.nw||u.old), src:u.old, slug, genre:'待识别', grade:'—', comp:'—', stage:0, status:'running', mode:0, human:null, cost:0, kb:u.kb, uploaded:true });
    });
    this.setState({ added:[...this.state.added, ...added], uploads:[], uploadOpen:false, sel:added[0].id, tab:'overview', dlOpen:false });
  }

  // ---- single-book download ----
  downloadBlob(name, text, mime){
    const blob=new Blob([text], {type:mime||'text/plain;charset=utf-8'});
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a'); a.href=url; a.download=name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(()=>URL.revokeObjectURL(url), 1500);
  }
  genFinal(b,d){
    let s='# '+b.title+'\n\n';
    s+='> 产线编号: '+(b.slug||b.id)+'\n';
    s+='> 源稿: 《'+(b.src||'—')+'》  →  《'+b.title+'》\n';
    s+='> 题材: '+b.genre+'  ·  准入: '+b.grade+'  ·  模式: '+this.MODE(b.mode)+'\n';
    s+='> 认证: '+(b.status==='certified'?'已认证出货':'未认证')+'  ·  人工成品分: '+(b.human==null?'—':b.human)+' / 95\n';
    s+='> 规格: 固定 60 章 · ~21 万字 · 原创换皮重写（保故事内核 · 禁逐字照搬）\n';
    s+='> 生成: HIKI fiction-rewrite v5.1 · '+this.todayStr()+'\n\n---\n\n';
    if(d&&d.scenes&&d.scenes.list&&d.scenes.list.length){
      s+='## 章节结构（节选）\n\n';
      d.scenes.list.forEach(sc=>{ s+='### 第 '+sc.n+' 章 · '+sc.beat+'\n'+(sc.type==='DRAMATIZE'?'_（戏剧化场景）_':'_（概述过渡）_')+'\n\n（正文略 …）\n\n'; });
    }
    s+='\n> 完整 60 章正文由 Assemble 阶段拼装输出，此处为交付结构摘要。\n';
    return s;
  }
  genAcceptance(b,d){
    const obj={ slug:b.slug||b.id, title:b.title, source_name:b.src||null, genre:b.genre,
      admission:{grade:b.grade, compressible:b.comp}, mode:this.MODE(b.mode),
      certified:b.status==='certified', verdict:b.status, human_score:b.human, target:95, ship_line:75,
      cost_cny:b.cost, budget_cap_cny:(this.props.budgetCap||50),
      dimensions: d&&d.dims? d.dims.reduce((o,x)=>{o[x.k]=x.v;return o;},{}) : null,
      gate: d&&d.gate? { mechanical:d.gate.mech.map(m=>({k:m.k,v:m.v,pass:m.pass})), pk:d.gate.pk.map(p=>({vs:p.vs,score:p.score,pass:p.pass})), book:d.gate.book.map(x=>({k:x.k,pass:x.pass})) } : null,
      review: d&&d.review? {total:d.review.total, comment:d.review.text, signal_snapshot:d.review.snapshot} : null,
      generated:'HIKI fiction-rewrite v5.1', date:this.todayStr() };
    return JSON.stringify(obj,null,2);
  }
  genLedger(b,d){
    const rows=(d&&d.cost)||[]; const totalUsd=rows.reduce((a,c)=>a+c.usd,0);
    const obj={ slug:b.slug||b.id, budget_cap_cny:(this.props.budgetCap||50),
      total_usd:+totalUsd.toFixed(2), total_cny:Math.round(totalUsd/0.14),
      rows: rows.map(c=>({stage:c.k, usd:c.usd, note:c.note})) };
    return JSON.stringify(obj,null,2);
  }

  TABS(){ return [
    {key:'overview', label:'概览'},
    {key:'dna', label:'DNA'},
    {key:'scenes', label:'场景'},
    {key:'gate', label:'闸门'},
    {key:'cost', label:'成本'},
    {key:'human', label:'人评'},
    {key:'spine', label:'Spine'},
  ]; }

  // ---- cross-book calibration: auto 承重信号 vs 人工承重 (near-zero corr) ----
  CALIB(){ return {
    note:'承重门微观信号（重演/spine/final）与人类承重判分 零相关；同文承重自评 ±40 抖动 → 已降 advisory（A）。',
    points:[
      {label:'隐婚', auto:71, human:62, c:'#3fb950'},
      {label:'退婚', auto:55, human:65, c:'#3fb950'},
      {label:'宅斗', auto:78, human:58, c:'#3fb950'},
      {label:'穿越', auto:60, human:55, c:'#58a6ff'},
      {label:'傲世', auto:82, human:38, c:'#f85149'},
    ],
  }; }

  DETAILS(){ return {
    hunyin:{
      dna:[
        {label:'脊柱 spine', v:'豪门隐婚→误会→揭身份→双向救赎', note:'5 卷主弧'},
        {label:'钩子账 hooks', v:'12 强钩 · 章均 0.9', note:'保源已验证钩子'},
        {label:'情感曲线 emotion', v:'虐30% · 甜55% · 燃15%', note:''},
        {label:'人物弧 arcs', v:'女主 隐忍→觉醒 · 男主 偏执→信任', note:''},
        {label:'伏笔 foreshadow', v:'7 处 · 全回收', note:''},
        {label:'爽点 payoffs', v:'打脸9 · 撒糖21 · 逆袭4', note:''},
        {label:'人名词典 names', v:'37 实体冻结', note:'→ Fact Spine'},
        {label:'语域指纹 voice', v:'轻快口语 + 内心独白', note:'cosine 基线'},
        {label:'题材 genre', v:'现代言情 · 隐婚 · 甜宠', note:''},
      ],
      scenes:{total:60,drafted:60,peaks:[12,28,44,57],list:[
        {n:1,type:'DRAMATIZE',beat:'婚礼现场认错人',status:'pass',cand:5,pk:'胜源 · 明显'},
        {n:12,type:'DRAMATIZE',beat:'身份揭穿 · 第一高点',status:'pass',cand:8,pk:'达金标'},
        {n:28,type:'DRAMATIZE',beat:'误会爆发 · 分离',status:'pass',cand:8,pk:'达金标'},
        {n:33,type:'SUMMARIZE',beat:'三个月后 · 过渡',status:'pass',cand:2,pk:'胜源'},
        {n:57,type:'DRAMATIZE',beat:'机场挽回 · 终章高点',status:'pass',cand:8,pk:'达金标'},
      ]},
      gate:{mech:[
        {k:'AI腔密度',v:'0.7%',pass:true,note:'阈 <3%'},
        {k:'风格 cosine vs 源',v:'0.86',pass:true,note:'换皮 0.6–0.9'},
        {k:'注水残留',v:'1.2%',pass:true,note:'五类注水'},
        {k:'语病/人名一致',v:'100%',pass:true,note:'37 实体'},
        {k:'结构合规',v:'60章 · 均3480字 · 4-beat',pass:true,note:'首章交代 ✓'},
        {k:'逐字重合',v:'4.1%',pass:true,note:'原创下限 <8%'},
      ],pk:[
        {vs:'本书源（下锚）',verdict:'明显胜',score:'82% 胜率',pass:true},
        {vs:'金标 95（上锚）',verdict:'临界达标',score:'48% 持平',pass:true},
        {vs:'标杆 90（近目标）',verdict:'略低',score:'43%',pass:true},
      ],book:[
        {k:'弧光收束',pass:true,note:''},{k:'节奏曲线',pass:true,note:''},
        {k:'主题统一',pass:true,note:''},{k:'结尾落点',pass:true,note:''},
        {k:'全书连续性审计',pass:true,note:'状态机·伏笔账·时间线 ✓'},
      ]},
      cost:[{k:'Extract',usd:0.20,note:'flash 首读 · 缓存'},{k:'Plan',usd:0.30,note:'pro 分层'},{k:'Draft',usd:0.26,note:'flash 主力'},{k:'锦标赛+精修',usd:0.90,note:'4 高点大 N'},{k:'闸门 PK',usd:2.60,note:'评估大头'}],
      dims:[{k:'承重',v:62},{k:'笔力',v:90},{k:'开篇代入',v:78},{k:'钩子爽点',v:80},{k:'节奏',v:76},{k:'人物',v:74}],
      review:{total:75,version:'gate@v5.1 · spine@on',mode:'M1 深度长评',text:'甜宠节奏到位，撒糖密度够；去套话重写后笔力跃至 90。承重尚可但中段两处人物动机断层。达出货线 75，当前最佳。',snapshot:[{k:'承重门信号',v:'0.71（虚高）'},{k:'笔力自评',v:'82'},{k:'PK 金标',v:'48%'}]},
      spine:[
        {group:'人物登记',items:[{name:'苏挽',attr:'女主 · 设计师 · 真千金',lock:true},{name:'霍司珩',attr:'男主 · 霍氏总裁',lock:true},{name:'苏曼',attr:'伪千金 · 反派',lock:true}]},
        {group:'关键物品',items:[{name:'翡翠镯',attr:'母亲遗物 · 认亲信物',lock:true}]},
        {group:'时间线',items:[{name:'隐婚→揭穿',attr:'第 3 年 · 第 12 章',lock:true}]},
      ],
    },
    tuihun:{
      dna:[
        {label:'脊柱 spine',v:'被退婚→打脸逆袭→真身份揭晓',note:'5 卷主弧'},
        {label:'钩子账 hooks',v:'15 强钩 · 章均 1.1',note:''},
        {label:'情感曲线 emotion',v:'憋屈25% · 爽65% · 暖10%',note:''},
        {label:'人物弧 arcs',v:'男主 隐忍→张扬 · 反派 步步崩',note:''},
        {label:'伏笔 foreshadow',v:'9 处 · 全回收',note:''},
        {label:'爽点 payoffs',v:'打脸17 · 逆袭8 · 升咖6',note:'爽文密度高'},
        {label:'人名词典 names',v:'41 实体冻结',note:''},
        {label:'语域指纹 voice',v:'快节奏 · 短句 · 金句',note:''},
        {label:'题材 genre',v:'都市爽文 · 退婚流',note:''},
      ],
      scenes:{total:60,drafted:60,peaks:[8,25,41,55],list:[
        {n:8,type:'DRAMATIZE',beat:'宴会当众打脸',status:'pass',cand:8,pk:'达金标'},
        {n:18,type:'SUMMARIZE',beat:'创业三月速写',status:'pass',cand:2,pk:'胜源'},
        {n:25,type:'DRAMATIZE',beat:'收购前东家 · 高点',status:'pass',cand:8,pk:'达金标'},
        {n:41,type:'DRAMATIZE',beat:'身份反转',status:'pass',cand:8,pk:'达金标'},
        {n:55,type:'DRAMATIZE',beat:'终局清算',status:'pass',cand:6,pk:'胜源 · 明显'},
      ]},
      gate:{mech:[
        {k:'AI腔密度',v:'0.9%',pass:true,note:'阈 <3%'},
        {k:'风格 cosine vs 源',v:'0.82',pass:true,note:''},
        {k:'注水残留',v:'1.6%',pass:true,note:''},
        {k:'语病/人名一致',v:'100%',pass:true,note:'41 实体'},
        {k:'结构合规',v:'60章 · 均3520字',pass:true,note:'首章交代 ✓'},
        {k:'逐字重合',v:'5.3%',pass:true,note:'<8%'},
      ],pk:[
        {vs:'本书源（下锚）',verdict:'明显胜',score:'88% 胜率',pass:true},
        {vs:'金标 95（上锚）',verdict:'达标',score:'51% 持平',pass:true},
        {vs:'标杆 90（近目标）',verdict:'持平',score:'49%',pass:true},
      ],book:[
        {k:'弧光收束',pass:true,note:''},{k:'节奏曲线',pass:true,note:'爽点节拍稳'},
        {k:'主题统一',pass:true,note:''},{k:'结尾落点',pass:true,note:''},
        {k:'全书连续性审计',pass:true,note:'✓'},
      ]},
      cost:[{k:'Extract',usd:0.20,note:''},{k:'Plan',usd:0.35,note:''},{k:'Draft',usd:0.30,note:'模式2'},{k:'锦标赛+精修',usd:1.40,note:'弱钩补强'},{k:'闸门 PK',usd:3.05,note:'评估大头'}],
      dims:[{k:'承重',v:65},{k:'笔力',v:86},{k:'开篇代入',v:80},{k:'钩子爽点',v:82},{k:'节奏',v:78},{k:'人物',v:76}],
      review:{total:76,version:'gate@v5.1 · spine@on',mode:'M1 深度长评',text:'B 源经强化改写反成全批最高分。爽点密度与节奏是强项，打脸节拍干净。承重略优于隐婚。证伪「选强源即选质量」——源档≠成品分。',snapshot:[{k:'承重门信号',v:'0.55'},{k:'笔力自评',v:'80'},{k:'PK 金标',v:'51%'}]},
      spine:[
        {group:'人物登记',items:[{name:'陆沉',attr:'男主 · 被退婚 · 隐藏富豪',lock:true},{name:'林氏',attr:'前未婚妻家 · 反派阵营',lock:true}]},
        {group:'关键物品',items:[{name:'退婚书',attr:'开篇导火索',lock:true}]},
        {group:'时间线',items:[{name:'退婚→收购',attr:'跨 8 个月',lock:true}]},
      ],
    },
    zhaidou:{
      dna:[
        {label:'脊柱 spine',v:'庶女觉醒→宅斗上位→谋得良缘',note:'5 卷主弧'},
        {label:'钩子账 hooks',v:'10 强钩 · 章均 0.8',note:''},
        {label:'情感曲线 emotion',v:'隐忍40% · 反击45% · 团圆15%',note:''},
        {label:'人物弧 arcs',v:'女主 怯懦→城府 · 嫡母 由盛转衰',note:''},
        {label:'伏笔 foreshadow',v:'8 处 · 回收 7',note:'1 处弱'},
        {label:'爽点 payoffs',v:'打脸11 · 智斗9',note:''},
        {label:'人名词典 names',v:'52 实体冻结',note:'人物密集'},
        {label:'语域指纹 voice',v:'半文半白 · 含蓄',note:''},
        {label:'题材 genre',v:'古代言情 · 宅斗',note:''},
      ],
      scenes:{total:60,drafted:60,peaks:[10,27,43,58],list:[
        {n:10,type:'DRAMATIZE',beat:'祠堂对质',status:'pass',cand:6,pk:'胜源'},
        {n:27,type:'DRAMATIZE',beat:'识破毒计 · 高点',status:'pass',cand:8,pk:'临界达标'},
        {n:43,type:'DRAMATIZE',beat:'扳倒嫡母',status:'pass',cand:8,pk:'胜源 · 明显'},
        {n:50,type:'SUMMARIZE',beat:'议亲过场',status:'pass',cand:2,pk:'胜源'},
        {n:58,type:'DRAMATIZE',beat:'凤冠加身',status:'pass',cand:6,pk:'临界'},
      ]},
      gate:{mech:[
        {k:'AI腔密度',v:'1.1%',pass:true,note:'阈 <3%'},
        {k:'风格 cosine vs 源',v:'0.79',pass:true,note:''},
        {k:'注水残留',v:'2.2%',pass:true,note:''},
        {k:'语病/人名一致',v:'98%',pass:true,note:'52 实体 · 1 处歧义'},
        {k:'结构合规',v:'60章 · 均3460字',pass:true,note:'✓'},
        {k:'逐字重合',v:'6.0%',pass:true,note:'<8%'},
      ],pk:[
        {vs:'本书源（下锚）',verdict:'胜',score:'74% 胜率',pass:true},
        {vs:'金标 95（上锚）',verdict:'临界',score:'41%',pass:true},
        {vs:'标杆 90（近目标）',verdict:'偏低',score:'38%',pass:true},
      ],book:[
        {k:'弧光收束',pass:true,note:''},{k:'节奏曲线',pass:true,note:'中段稍缓'},
        {k:'主题统一',pass:true,note:''},{k:'结尾落点',pass:true,note:''},
        {k:'全书连续性审计',pass:true,note:'52 实体 · 时间线 ✓'},
      ]},
      cost:[{k:'Extract',usd:0.22,note:''},{k:'Plan',usd:0.32,note:''},{k:'Draft',usd:0.27,note:''},{k:'锦标赛+精修',usd:0.85,note:''},{k:'闸门 PK',usd:2.70,note:''}],
      dims:[{k:'承重',v:58},{k:'笔力',v:82},{k:'开篇代入',v:70},{k:'钩子爽点',v:72},{k:'节奏',v:70},{k:'人物',v:68}],
      review:{total:68,version:'gate@v5.1 · spine@on',mode:'M1 深度长评',text:'低空认证。宅斗智斗线扎实，但人物过多导致中段承重吃紧，承重 58 偏低拖总分。笔力达标。',snapshot:[{k:'承重门信号',v:'0.78（明显虚高）'},{k:'笔力自评',v:'78'},{k:'PK 金标',v:'41%'}]},
      spine:[
        {group:'人物登记',items:[{name:'沈微',attr:'女主 · 庶女',lock:true},{name:'沈夫人',attr:'嫡母 · 反派',lock:true},{name:'裴砚',attr:'男主 · 世子',lock:true}]},
        {group:'世界观设定',items:[{name:'沈府嫡庶制',attr:'核心冲突场域',lock:true}]},
        {group:'时间线',items:[{name:'觉醒→议亲',attr:'跨 2 年',lock:true}]},
      ],
    },
    chuanyue:{
      dna:[
        {label:'脊柱 spine',v:'重生回高考年→改命复仇→守护所爱',note:'5 卷主弧'},
        {label:'钩子账 hooks',v:'11 强钩 · 章均 0.85',note:''},
        {label:'情感曲线 emotion',v:'遗憾30% · 逆转50% · 圆满20%',note:''},
        {label:'人物弧 arcs',v:'主角 悔恨→笃定',note:''},
        {label:'伏笔 foreshadow',v:'6 处 · 规划中',note:''},
        {label:'爽点 payoffs',v:'先知8 · 打脸6',note:''},
        {label:'人名词典 names',v:'33 实体冻结',note:''},
        {label:'语域指纹 voice',v:'第一人称 · 回忆体',note:'代入感关键'},
        {label:'题材 genre',v:'穿越重生 · 都市',note:''},
      ],
      scenes:{total:60,drafted:34,peaks:[9,26,42,56],list:[
        {n:1,type:'DRAMATIZE',beat:'重生睁眼 · 开篇代入',status:'pass',cand:8,pk:'胜源（铁律B 复核）'},
        {n:9,type:'DRAMATIZE',beat:'阻止那场车祸 · 高点',status:'pass',cand:8,pk:'临界达标'},
        {n:26,type:'DRAMATIZE',beat:'高考逆袭',status:'running',cand:6,pk:'评估中'},
        {n:34,type:'SUMMARIZE',beat:'大学过渡',status:'pending',cand:0,pk:'排队'},
        {n:42,type:'DRAMATIZE',beat:'商战先手',status:'pending',cand:0,pk:'排队'},
      ]},
      gate:{mech:[
        {k:'AI腔密度',v:'1.4%',pass:true,note:'已草稿章'},
        {k:'风格 cosine vs 源',v:'0.81',pass:true,note:''},
        {k:'注水残留',v:'2.8%',pass:true,note:''},
        {k:'语病/人名一致',v:'99%',pass:true,note:'33 实体'},
        {k:'结构合规',v:'34/60 章草稿',pass:null,note:'进行中'},
        {k:'逐字重合',v:'5.7%',pass:true,note:'<8%'},
      ],pk:[
        {vs:'本书源（下锚）',verdict:'胜',score:'70%（已评章）',pass:true},
        {vs:'金标 95（上锚）',verdict:'未达',score:'34%',pass:false},
        {vs:'标杆 90（近目标）',verdict:'未评',score:'—',pass:null},
      ],book:[
        {k:'整本级审计',pass:null,note:'待全本草稿完成'},
      ]},
      cost:[{k:'Extract',usd:0.21,note:''},{k:'Plan',usd:0.33,note:''},{k:'Draft',usd:0.16,note:'34/60 进行中'},{k:'锦标赛+精修',usd:0.42,note:'部分高点'},{k:'闸门 PK',usd:0.0,note:'整本闸门未起'}],
      dims:[{k:'承重',v:55},{k:'笔力',v:75},{k:'开篇代入',v:48},{k:'钩子爽点',v:68},{k:'节奏',v:64},{k:'人物',v:62}],
      review:{total:63,version:'gate@v5.1 · 试评',mode:'M2 试评（盲）',text:'human-eval-5 命中铁律 B：穿越·重生开篇代入感弱（48）是主短板，第 1 章已按「重生开篇铁律」复写复核。中段笔力尚可，承重待全本审计。',snapshot:[{k:'承重门信号',v:'0.60'},{k:'笔力自评',v:'72'},{k:'PK 金标',v:'34%'}]},
      spine:[
        {group:'人物登记',items:[{name:'江野',attr:'主角 · 重生者',lock:true},{name:'苏念',attr:'女主 · 待救者',lock:true}]},
        {group:'时间线',items:[{name:'重生锚点',attr:'高考前 90 天 · 硬约束',lock:true},{name:'车祸事件',attr:'第 9 章 · 不可早于',lock:true}]},
      ],
    },
    aoshi:{
      dna:[
        {label:'脊柱 spine',v:'废材觉醒→宗门崛起→证道苍穹',note:'7 卷 · 体量大'},
        {label:'钩子账 hooks',v:'14 钩 · 章均 1.0',note:'源钩偏套路'},
        {label:'情感曲线 emotion',v:'热血70% · 悲壮20% · 暧昧10%',note:''},
        {label:'人物弧 arcs',v:'主角 弱→强（线性 · 缺转折）',note:'弧光单薄'},
        {label:'伏笔 foreshadow',v:'12 处 · 多处断裂',note:'承重隐患'},
        {label:'爽点 payoffs',v:'升级22 · 打脸15',note:'数值刷屏'},
        {label:'人名词典 names',v:'88 实体 · 冲突 6',note:'设定打架'},
        {label:'语域指纹 voice',v:'夸张 · 套话密',note:'去套话压力大'},
        {label:'题材 genre',v:'玄幻 · 升级流',note:''},
      ],
      scenes:{total:60,drafted:60,peaks:[14,30,46,59],list:[
        {n:14,type:'DRAMATIZE',beat:'宗门大比',status:'pass',cand:8,pk:'胜源'},
        {n:30,type:'DRAMATIZE',beat:'灭门复仇 · 高点',status:'fail',cand:8,pk:'未达金标 · 承重断'},
        {n:46,type:'DRAMATIZE',beat:'秘境夺宝',status:'fail',cand:8,pk:'设定冲突'},
        {n:52,type:'SUMMARIZE',beat:'闭关三年',status:'pass',cand:2,pk:'胜源'},
        {n:59,type:'DRAMATIZE',beat:'证道终战',status:'fail',cand:8,pk:'弧光未收束'},
      ]},
      gate:{mech:[
        {k:'AI腔密度',v:'2.1%',pass:true,note:'阈 <3%'},
        {k:'风格 cosine vs 源',v:'0.74',pass:true,note:''},
        {k:'注水残留',v:'3.6%',pass:false,note:'超阈 · 数值流难压'},
        {k:'语病/人名一致',v:'91%',pass:false,note:'88 实体 · 6 冲突'},
        {k:'结构合规',v:'60章 · 体量压缩损钩',pass:true,note:'勉强'},
        {k:'逐字重合',v:'7.6%',pass:true,note:'临界 <8%'},
      ],pk:[
        {vs:'本书源（下锚）',verdict:'胜',score:'66% 胜率',pass:true},
        {vs:'金标 95（上锚）',verdict:'明显未达',score:'22%',pass:false},
        {vs:'标杆 90（近目标）',verdict:'差距大',score:'19%',pass:false},
      ],book:[
        {k:'弧光收束',pass:false,note:'终战未收束'},{k:'节奏曲线',pass:true,note:''},
        {k:'主题统一',pass:true,note:''},{k:'结尾落点',pass:false,note:'仓促'},
        {k:'全书连续性审计',pass:false,note:'设定冲突6 · 伏笔断裂 · 承重崩'},
      ]},
      cost:[{k:'Extract',usd:0.28,note:'体量大'},{k:'Plan',usd:0.45,note:'7卷压60章'},{k:'Draft',usd:0.40,note:''},{k:'锦标赛+精修',usd:2.10,note:'反复救场'},{k:'闸门 PK',usd:3.40,note:'多轮重评'}],
      dims:[{k:'承重',v:38},{k:'笔力',v:70},{k:'开篇代入',v:52},{k:'钩子爽点',v:60},{k:'节奏',v:55},{k:'人物',v:50}],
      review:{total:54,version:'gate@v5.1 · spine@on',mode:'M1 深度长评',text:'全批最低。S 源（pregrade 高）≠ 人类成品分——升级流大体量压成 60 章后伏笔断裂、设定冲突，承重崩至 38，是质量瓶颈的极端样本。模式3 重构仍救不动 → 拒收。',snapshot:[{k:'承重门信号',v:'0.82（严重虚高）'},{k:'笔力自评',v:'76'},{k:'PK 金标',v:'22%'}]},
      spine:[
        {group:'人物登记',items:[{name:'萧战',attr:'主角 · 废材→帝',lock:true},{name:'药尘',attr:'师尊 · 设定冲突',lock:false}]},
        {group:'世界观设定',items:[{name:'境界体系',attr:'9 大境 · 跨卷数值打架',lock:false},{name:'秘境规则',attr:'第30/46章 自相矛盾',lock:false}]},
        {group:'时间线',items:[{name:'闭关跨度',attr:'与年龄线冲突',lock:false}]},
      ],
    },
    wendao:{
      dna:[
        {label:'脊柱 spine',v:'凡人问道 → 抽取中…',note:'Extract 进行'},
        {label:'钩子账 hooks',v:'识别中',note:''},
        {label:'人名词典 names',v:'29 实体 · 登记中',note:''},
        {label:'题材 genre',v:'仙侠 · 修真',note:'已定档'},
      ],
      scenes:null,gate:null,dims:null,review:null,
      cost:[{k:'Extract',usd:0.14,note:'flash 首读进行'}],
      spine:[{group:'人物登记',items:[{name:'秦渊',attr:'主角 · 登记中',lock:false}]}],
    },
    xingji:{
      dna:[
        {label:'脊柱 spine',v:'机甲少年→星海征途→守护文明',note:'弱源 · 钩子稀'},
        {label:'钩子账 hooks',v:'6 钩 · 章均 0.4',note:'偏少 · 需补强'},
        {label:'情感曲线 emotion',v:'识别中',note:''},
        {label:'人物弧 arcs',v:'规划中',note:''},
        {label:'人名词典 names',v:'45 实体冻结',note:''},
        {label:'语域指纹 voice',v:'硬科幻 · 术语密',note:''},
        {label:'题材 genre',v:'科幻 · 机甲',note:''},
      ],
      scenes:{total:60,drafted:0,peaks:[],list:[
        {n:1,type:'DRAMATIZE',beat:'机甲启动 · 规划中',status:'pending',cand:0,pk:'未起'},
        {n:'…',type:'—',beat:'outline_60 生成中（pro）',status:'pending',cand:0,pk:'—'},
      ]},
      gate:null,dims:null,review:null,
      cost:[{k:'Extract',usd:0.30,note:'D 弱源 · 多块'},{k:'Plan',usd:0.18,note:'规划进行'}],
      spine:[{group:'人物登记',items:[{name:'凌霄',attr:'主角 · 机师',lock:true}]},{group:'世界观设定',items:[{name:'星历纪元',attr:'设定登记中',lock:false}]}],
    },
    qiandao:{
      dna:null,scenes:null,gate:null,dims:null,review:null,
      cost:[{k:'Ingest',usd:0.14,note:'flash 清洗 · 唯一开销'}],
      spine:null,
    },
  }; }

  renderVals(){
    const accent = this.props.accent || '#4ec9b0';
    const budgetCap = this.props.budgetCap || 50;
    const books = [...this.BOOKS(), ...this.state.added];
    const selB = books.find(b=>b.id===this.state.sel) || books[0];

    // ---- sidebar list ----
    const dotColor = {done:'#3fb950', active:'#58a6ff', fail:'#f85149', pending:'#262d36'};
    const list = books.map(b=>{
      const si=this.statusInfo(b);
      const selected = b.id===this.state.sel;
      const sts=this.states(b);
      return {
        id:b.id, title:b.title, genre:b.genre, grade:b.grade,
        gradeColor:this.gC(b.grade), gradeBg:'rgba(255,255,255,.02)',
        titleColor: selected?'#fff':'#cdd5de',
        humanLabel: b.human==null?'—':String(b.human),
        humanColor:this.humanColor(b.human),
        statusText:si.text, statusColor:si.color,
        cardBg: selected?'#161f2b':'transparent',
        cardBorder: selected?'#2b3a4d':'transparent',
        dots: sts.map(s=>({c:dotColor[s]})),
        onSelect:()=>this.selectBook(b.id),
      };
    });

    // ---- pipeline flow for selected ----
    const sts=this.states(selB);
    const stageDefs=this.STAGES();
    const badgeBg={done:'#3fb950',active:'#58a6ff',fail:'#f85149',pending:'transparent'};
    const badgeColor={done:'#08120f',active:'#08120f',fail:'#fff',pending:'#5c6672'};
    const badgeBorder={done:'#3fb950',active:'#58a6ff',fail:'#f85149',pending:'#2b333d'};
    const modelStyle={pro:{c:'#bc8cff',b:'rgba(188,140,255,.12)'},flash:{c:'#39c5cf',b:'rgba(57,197,207,.12)'},'pro·flash':{c:'#9aa6ff',b:'rgba(154,166,255,.1)'},'—':{c:'#5c6672',b:'rgba(255,255,255,.03)'}};
    const flow=[];
    stageDefs.forEach((sd,i)=>{
      const s=sts[i];
      const ms=modelStyle[sd.model]||modelStyle['—'];
      flow.push({ isNode:true, isLink:false,
        mark: s==='done'?'✓' : s==='fail'?'✕' : String(i),
        name:sd.name, sub:sd.cn, model:sd.model,
        badgeBg:badgeBg[s], badgeColor:badgeColor[s], badgeBorder:badgeBorder[s],
        nameColor: s==='pending'?'#5c6672':'#cdd5de',
        anim: s==='active'?'hpulse 1.4s ease-in-out infinite':'none',
        modelColor:ms.c, modelBg:ms.b });
      if(i<stageDefs.length-1){
        const nextDone = sts[i+1]==='done';
        const nextActive = sts[i+1]==='active';
        flow.push({ isLink:true, isNode:false, color: nextDone?'#3fb950':(nextActive?'#3a5a86':'#1c232c') });
      }
    });

    // ---- tabs ----
    const tabs=this.TABS().map(t=>({
      label:t.label, badge:'', badgeColor:'#5c6672',
      onClick:()=>this.selectTab(t.key),
      color: this.state.tab===t.key?'#fff':'#7d8590',
      weight: this.state.tab===t.key?'700':'500',
      underline: this.state.tab===t.key?accent:'transparent',
    }));

    // ---- selected detail ----
    const si=this.statusInfo(selB);
    const capPct=Math.min(100,Math.round(selB.cost/budgetCap*100));
    const capColor = capPct>90?'#f85149' : capPct>70?'#d29922':'#3fb950';
    const stageDef=stageDefs[selB.stage];

    // ---- detail processing ----
    const det = this.DETAILS()[selB.id] || {};
    const dimColor = v => v>=80?'#3fb950' : v>=68?'#7fc94a' : v>=55?'#d29922' : '#f0883e';
    const passView = p => p===true?{t:'通过',c:'#3fb950',i:'✓'} : p===false?{t:'未过',c:'#f85149',i:'✕'} : {t:'进行',c:'#d29922',i:'⋯'};
    const pendingNote = '⋯ 数据将在后续阶段产出 · 当前 '+stageDef.name+' · '+stageDef.cn;

    const hasDna = !!(det.dna && det.dna.length);
    const dnaItems = (det.dna||[]).map(d=>({label:d.label, v:d.v, note:d.note||'', hasNote:!!d.note}));

    let scenes=null;
    if(det.scenes){
      const sc=det.scenes;
      const tcol=t=>t==='DRAMATIZE'?'#4ec9b0' : t==='SUMMARIZE'?'#8b949e' : '#5c6672';
      scenes={ total:sc.total, drafted:sc.drafted, draftPct:Math.round(sc.drafted/sc.total*100)+'%',
        peaks: sc.peaks.length?('CH '+sc.peaks.join(' · ')):'—', peakCount:sc.peaks.length,
        list: sc.list.map(s=>({ n:s.n, type:s.type, typeColor:tcol(s.type), beat:s.beat, cand:s.cand, pk:s.pk,
          statusColor: s.status==='pass'?'#3fb950' : s.status==='fail'?'#f85149' : s.status==='running'?'#58a6ff' : '#5c6672',
          statusBg: s.status==='pass'?'rgba(63,185,80,.1)' : s.status==='fail'?'rgba(248,81,73,.1)' : s.status==='running'?'rgba(88,166,255,.1)' : 'rgba(255,255,255,.03)',
          statusText: s.status==='pass'?'通过' : s.status==='fail'?'未过' : s.status==='running'?'评估中' : '排队' })) };
    }
    const hasScenes=!!scenes;

    let gate=null;
    if(det.gate){
      gate={ mech:(det.gate.mech||[]).map(m=>{const pv=passView(m.pass);return {k:m.k,v:m.v,note:m.note,c:pv.c,i:pv.i,t:pv.t};}),
        pk:(det.gate.pk||[]).map(p=>{const pv=passView(p.pass);return {vs:p.vs,verdict:p.verdict,score:p.score,c:pv.c,i:pv.i};}),
        book:(det.gate.book||[]).map(b=>{const pv=passView(b.pass);return {k:b.k,note:b.note||'',hasNote:!!b.note,c:pv.c,i:pv.i,t:pv.t};}) };
    }
    const hasGate=!!gate;

    const costRaw = det.cost||[];
    const maxUsd = Math.max(0.01, ...costRaw.map(c=>c.usd));
    const totalUsd = costRaw.reduce((a,c)=>a+c.usd,0);
    const isGateRow = k=>/闸门|PK/.test(k);
    const costRows = costRaw.map(c=>({ k:c.k, usd:'$'+c.usd.toFixed(2), note:c.note,
      pct:Math.round(c.usd/maxUsd*100)+'%', barColor:isGateRow(c.k)?'#bc8cff':'#4ec9b0',
      kColor:isGateRow(c.k)?'#bc8cff':'#cdd5de' }));
    const costTotalUsd='$'+totalUsd.toFixed(2);
    const costTotalCny=Math.round(totalUsd/0.14);
    const costCapPct=Math.min(100,Math.round(costTotalCny/budgetCap*100))+'%';
    const costCapColor = costTotalCny/budgetCap>0.9?'#f85149' : costTotalCny/budgetCap>0.7?'#d29922':'#3fb950';

    const hasHuman=!!det.dims;
    const dims = det.dims ? det.dims.map(d=>({ k:d.k, label:d.k==='承重'?'承重 · 瓶颈':d.k, v:d.v, pct:d.v+'%', color:dimColor(d.v), weight:d.k==='承重'?'700':'400' })) : [];
    const review = det.review || null;

    const hasSpine=!!(det.spine && det.spine.length);
    const spineGroups = det.spine ? det.spine.map(g=>({ group:g.group, count:g.items.length, items:g.items.map(it=>({
      name:it.name, attr:it.attr, lockText:it.lock?'冻结':'冲突', lockColor:it.lock?'#4ec9b0':'#f0883e',
      lockBg:it.lock?'rgba(78,201,176,.1)':'rgba(240,136,62,.12)', lockBorder:it.lock?'rgba(78,201,176,.3)':'rgba(240,136,62,.35)' })) })) : [];
    const spineConflicts = det.spine ? det.spine.reduce((a,g)=>a+g.items.filter(i=>!i.lock).length,0) : 0;

    const calibRaw=this.CALIB();
    const calib={ note:calibRaw.note, points: calibRaw.points.map(p=>({ label:p.label, auto:p.auto, human:p.human, c:p.c, x:p.auto+'%', y:p.human+'%', cur:p.label===selB.title.split('·')[0]?true:false })) };

    // ---- naming / download / upload view-models ----
    const date=this.todayStr();
    const uploaded=!!selB.uploaded;
    const slug=selB.slug||selB.id;
    const src=selB.src||'—';
    const subtitle = uploaded
      ? ('源《'+src+'》 · 题材待识别 · 准入评级中')
      : (selB.genre+' · 源档 '+selB.grade+'（可压缩 '+selB.comp+'） · '+this.MODE(selB.mode));
    let spineSt, spineCol;
    if(selB.grade==='Q'){ spineSt='未启用'; spineCol='#5c6672'; }
    else if(selB.stage<1){ spineSt='待建'; spineCol='#d29922'; }
    else if(selB.status==='running'&&selB.stage<3){ spineSt='登记中'; spineCol='#d29922'; }
    else { spineSt='已冻结'; spineCol='#4ec9b0'; }

    const detRaw=this.DETAILS()[selB.id]||null;
    const canDl=selB.status==='certified';
    const canDiag=selB.status==='rejected' && selB.grade!=='Q';
    const dlItems=[];
    if(canDl){
      dlItems.push({name:'final.md', desc:'成品正文 · 60 章拼装', tag:'MD', tagColor:'#4ec9b0', onClick:()=>this.downloadBlob(slug+'.final.md', this.genFinal(selB,detRaw),'text/markdown;charset=utf-8')});
      dlItems.push({name:'acceptance.json', desc:'验收报告 · 认证/分数/闸门', tag:'JSON', tagColor:'#58a6ff', onClick:()=>this.downloadBlob(slug+'.acceptance.json', this.genAcceptance(selB,detRaw),'application/json')});
      dlItems.push({name:'cost_ledger.json', desc:'成本账本', tag:'JSON', tagColor:'#58a6ff', onClick:()=>this.downloadBlob(slug+'.cost_ledger.json', this.genLedger(selB,detRaw),'application/json')});
    } else if(canDiag){
      dlItems.push({name:'diagnostic.json', desc:'拒收诊断 · 失败维度/闸门', tag:'JSON', tagColor:'#f0883e', onClick:()=>this.downloadBlob(slug+'.diagnostic.json', this.genAcceptance(selB,detRaw),'application/json')});
      dlItems.push({name:'cost_ledger.json', desc:'成本账本', tag:'JSON', tagColor:'#58a6ff', onClick:()=>this.downloadBlob(slug+'.cost_ledger.json', this.genLedger(selB,detRaw),'application/json')});
    }
    const dlActive=canDl||canDiag;
    const dl={ open:this.state.dlOpen && dlActive, canDownload:dlActive,
      cursor: dlActive?'pointer':'default',
      btnLabel: canDl?'下载成品' : canDiag?'下载诊断' : (selB.grade==='Q'?'Q · 无成品':'进行中 · 无成品'),
      btnColor: canDl?'#3fb950' : canDiag?'#f0883e' : '#5c6672',
      btnBg: canDl?'rgba(63,185,80,.1)' : canDiag?'rgba(240,136,62,.08)':'rgba(255,255,255,.02)',
      btnBorder: canDl?'rgba(63,185,80,.4)' : canDiag?'rgba(240,136,62,.35)':'#232b36',
      toggle:()=>{ if(dlActive) this.setState({dlOpen:!this.state.dlOpen}); },
      close:()=>this.setState({dlOpen:false}),
      items:dlItems, hasAll:canDl, onAll:()=>{ dlItems.forEach((it,i)=>setTimeout(it.onClick, i*220)); },
      title: canDl?('成品交付 · output/'+slug+'/'):('拒收诊断 · '+slug) };

    const ups=this.state.uploads.map(u=>({ uid:u.uid, old:u.old, nw:u.nw, kb:u.kb,
      slug:this.makeSlug(u.old, u.nw||u.old),
      onName:(e)=>this.setUpName(u.uid, e.target.value), onRemove:()=>this.removeUp(u.uid) }));
    const up={ open:this.state.uploadOpen, close:()=>this.closeUpload(),
      trigger:()=>this.triggerFile(), onFiles:(e)=>this.onFiles(e.target.files),
      onDrop:(e)=>{e.preventDefault(); this.onFiles(e.dataTransfer.files);}, onOver:(e)=>e.preventDefault(),
      files:ups, hasFiles:ups.length>0, empty:ups.length===0, count:ups.length, today:date,
      commit:()=>this.commitUploads(),
      commitCursor: ups.length>0?'pointer':'default',
      commitColor: ups.length>0?'#08120f':'#5c6672',
      commitBg: ups.length>0?'#4ec9b0':'#1c232c' };

    // ---- globals ----
    const certified=books.filter(b=>b.status==='certified').length;
    const rejected=books.filter(b=>b.status==='rejected').length;
    const finished=certified+rejected;
    const avg=Math.round(books.filter(b=>b.status==='certified').reduce((a,b)=>a+b.cost,0)/Math.max(1,certified));

    return {
      accent, budgetCap,
      books:list, flow, tabs,
      show:{ overview:this.state.tab==='overview', dna:this.state.tab==='dna', scenes:this.state.tab==='scenes', gate:this.state.tab==='gate', cost:this.state.tab==='cost', human:this.state.tab==='human', spine:this.state.tab==='spine' },
      g:{ total:books.length, certified, rejectRate:Math.round(rejected/Math.max(1,finished)*100)+'%', avgCost:avg },
      sel:{
        title:selB.title, genre:selB.genre, grade:selB.grade, comp:selB.comp,
        gradeColor:this.gC(selB.grade), gradeBg:'rgba(255,255,255,.02)',
        statusText:si.text, statusColor:si.color, statusBg:si.bg,
        modeText:this.MODE(selB.mode), modeNote:this.MODENOTE(selB.mode),
        cost:selB.cost, capPct:capPct+'%', capColor,
        human: selB.human, humanBig: selB.human==null?'—':String(selB.human),
        humanColor:this.humanColor(selB.human),
        certNote:this.certNote(selB),
        stageLabel: stageDef.name+' · '+stageDef.cn, stageNote:this.stageNote(selB),
        spineState: spineSt, spineColor: spineCol,
        subtitle, slug, src, uploaded,
      },
      dl, up, openUpload:()=>this.openUpload(),
      det:{ hasDna, noDna:!hasDna, dnaItems, hasScenes, noScenes:!hasScenes, scenes, hasGate, noGate:!hasGate, gate, costRows, costTotalUsd, costTotalCny, costCapPct, costCapColor, hasHuman, noHuman:!hasHuman, dims, review, hasReview:!!review, hasSpine, noSpine:!hasSpine, spineGroups, spineConflicts, hasConflicts:spineConflicts>0, pendingNote },
      calib,
    };
  }
}
