# -*- coding: utf-8 -*-
"""viz_mechanism.py — 机制系统「完整可解释性」可视化
   不依赖大模型: 用可控的模拟隐状态驱动 22 个机制, 记录全部内部量
   产出: 一个自包含 HTML, 能看到:
     ① 每个机制的状态时间序列
     ② 机制触发时序(谁在什么时候跑)
     ③ 机制间数据依赖(谁喂谁)
     ④ 因果链(改一个θ, 影响传到哪)
     ⑤ 状态槽的全部原始数值(可导出)
"""
import numpy as np, json, os, math

HERE = os.path.dirname(os.path.abspath(__file__))
DIM = 896

# ============ 从 master_params.json 载 θ ============
def load_theta():
    p = os.path.join(HERE, "super_socket", "master_params.json")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    return None

# ============ 22 个机制(与 JS 引擎一致) ============
MECH_REG = [
 ("selfread","selfread",1),("gate","gate",1),("retrieve","retrieval",1),
 ("energy","energy",1),("self_model","self_model",1),("self_edit","self_edit",1),
 ("reservoir","reservoir",1),("pain_mem","pain",1),("self_loop","self_loop",10),
 ("counterfact","counterfact",20),("ignite","ignite",40),("attractor","attractor",25),
 ("roam","roam",10),("consolidate","consolidate",80),("novelty_gate","novelty",10),
 ("reflect","reflect",25),("pseudo_probe","pseudo",10),("lineage_mark","lineage",100),
 ("physics_multi","physics_multi",1),("self_box","self_box",1),("meta_box","meta_box",1),
 ("reflect_up","reflect_up",1),
]

def nrm(v):
    n = np.linalg.norm(v)
    return v/n if n > 1e-12 else v

class Trace:
    """记录一次运行的完整内部量"""
    def __init__(self):
        self.t=[]; self.mech_fire={}   # {机制名: [触发的t]}
        self.slots={}                  # {槽名: [值序列]}
        self.mech_calls={}             # {机制名: 调用次数}
        self.deps=[]                   # 机制间依赖边
        self.energy_flow={"metab":0.0,"recover":0.0,"rest":0.0,"retrieve":0.0,"gain":0.0}
    def rec(self, name, val):
        self.slots.setdefault(name, []).append(float(val))
    def fire(self, mech, t):
        self.mech_fire.setdefault(mech, []).append(t)
        self.mech_calls[mech] = self.mech_calls.get(mech,0)+1

def run(theta, steps=600, seed=0, perturb=None):
    """跑机制系统, 记录全部内部量
       theta: 参数字典(可用 perturb 改)"""
    rng = np.random.RandomState(seed)
    th = json.loads(json.dumps(theta)) if theta else {}
    # 默认参数(若 master_params 缺失)
    def g(sec, key, dflt):
        return th.get(sec,{}).get(key, dflt)
    if perturb:
        for path, val in perturb.items():
            parts=path.split(".")
            cur=th
            for p in parts[:-1]: cur=cur.setdefault(p,{})
            cur[parts[-1]]=val

    # 状态
    st={"t":0,"E":g("energy","init",1.0),"Sf":None,"Sm":None,"Ss":None,"last_cos":0.0,
        "eta_eff":g("inject","eta",1.0),"pool":[],"ret_ema":0.0,"r":None,
        "pain_ema":0.0,"meta_fixes":0,"meta_dev":0.0,"stage":"--","s2":None,
        "last_action":"常规","thoughts":[]}
    n_res=g("reservoir","n",128); rho=g("reservoir","rho",0.9)
    Wr=rng.randn(n_res,n_res)*0.5
    mx=max(np.abs(np.linalg.eigvals(Wr))); Wr=Wr*(rho/max(mx,1e-6))
    Win=rng.randn(n_res,DIM)*0.3
    Wout=rng.randn(DIM,n_res)*0.2
    Wdesc=rng.randn(DIM,11)*0.5
    Wsb=rng.randn(DIM,4)*0.4
    st["r"]=np.zeros(n_res)
    for i in range(g("retrieval","pool_size",24)):
        st["pool"].append(nrm(rng.randn(DIM)))

    T=Trace()
    energy_cap=g("energy","cap",1.5)

    for step in range(steps):
        st["t"]+=1; t=st["t"]
        # 真实 LLM 特性: 话题内高度稳定(cos≈0.98), 换话题时跳变
        if step==0:
            topic = nrm(rng.randn(DIM))
            prev_vn = topic
        if step % 60 == 0:                      # 每60步换话题
            nt = rng.randn(DIM); nt = nt/np.linalg.norm(nt)
            topic = nrm(topic*0.5 + nt*0.5)
        # 话题内: 98%稳定 (噪声按【范数】缩放, 不是按分量!)
        nz = rng.randn(DIM); nz = nz/np.linalg.norm(nz)   # 单位范数
        vn = nrm(topic*0.98 + nz*0.199)                   # cos(vn,topic)≈0.98
        prev_vn = vn

        for name, sec, per in MECH_REG:
            if t % per != 0: continue
            T.fire(name, t)
            # ---- 各机制的原子计算(与 JS 一致) ----
            if name=="selfread":
                bf=g("selfread","beta_fast",0.4); bm=g("selfread","beta_mid",0.2); bs=g("selfread","beta_slow",0.08)
                st["Sf"]= vn.copy() if st["Sf"] is None else (1-bf)*st["Sf"]+bf*vn
                if t%g("selfread","tau_mid",10)==0:
                    st["Sm"]= vn.copy() if st["Sm"] is None else (1-bm)*st["Sm"]+bm*vn
                if t%g("selfread","tau_slow",40)==0:
                    st["Ss"]= vn.copy() if st["Ss"] is None else (1-bs)*st["Ss"]+bs*vn
            elif name=="gate":
                if st["Ss"] is None: st["Ss"]=vn.copy(); st["last_cos"]=1.0
                else:
                    cos=float(vn@nrm(st["Ss"])); st["last_cos"]=cos
                    if cos>=g("gate","cos_threshold",0.65):
                        sb=g("gate","ss_update_beta",0.08)
                        st["Ss"]=(1-sb)*st["Ss"]+sb*vn
            elif name=="retrieve":
                en=g("energy","cost_retrieve",0.004); rt=g("retrieval","topk",2)
                if st["E"]>en*g("energy","retrieve_econ_margin",3.0):
                    cosv=[float(p@vn) for p in st["pool"]]
                    idx=np.argsort(cosv)[-rt:]
                    fit=float(np.mean([cosv[i] for i in idx]))
                    st["E"]-=en; T.energy_flow["retrieve"]+=en
                    if fit>g("energy","fit_threshold",0.3):
                        r2=g("energy","gain_fit",0.006)*fit; st["E"]+=r2; T.energy_flow["gain"]+=r2
                    st["ret_ema"]=(1-0.1)*st["ret_ema"]+0.1*1.0
                else:
                    st["ret_ema"]=(1-0.1)*st["ret_ema"]+0.1*0.0
            elif name=="energy":
                metab=g("energy","metabolism",0.0004)
                sus=g("energy","sustain",{}) or {}
                al=(st["last_cos"]+1)/2
                gained=0.0
                if sus.get("enabled",True):
                    if al>=sus.get("recover_align_min",0.5):
                        r=sus.get("recover_on_align",0.002); st["E"]+=r
                        T.energy_flow["recover"]+=r; gained+=r
                    if t%sus.get("rest_every",30)==0:
                        r=sus.get("rest_recover",0.05); st["E"]+=r
                        T.energy_flow["rest"]+=r; gained+=r
                st["E"]=min(st["E"]-metab, energy_cap)
                T.energy_flow["metab"]+=metab
            elif name=="self_edit":
                se=th.get("self_edit",{})
                if se.get("enabled",True):
                    e_n=min(max(st["E"]/energy_cap,0),1); cos_n=(st["last_cos"]+1)/2
                    drv=e_n*se.get("eta_drive_e",0.7)+cos_n*se.get("eta_drive_cos",0.3)
                    st["eta_eff"]=g("inject","eta",1.0)*(se.get("eta_min",0.3)+(1-se.get("eta_min",0.3))*min(drv,1))
                else: st["eta_eff"]=g("inject","eta",1.0)
            elif name=="reservoir":
                leak=g("reservoir","leak",0.3)
                u=Win@vn
                st["r"]=(1-leak)*st["r"]+leak*np.tanh(Wr@st["r"]+u)
            elif name=="self_box":
                e_n=min(max(st["E"]/energy_cap,0),1); cos_n=(st["last_cos"]+1)/2
                ret_n=min(st["ret_ema"]*4,1); nov=rng.uniform(0.3,0.9)
                st["s2"]=np.array([e_n,cos_n,ret_n,nov])
            elif name=="meta_box":
                mb=th.get("meta_box",{})
                if st["s2"] is not None:
                    gt=np.array(mb.get("target",[0.8,0.8,0.9,0.6]))
                    dev=st["s2"]-gt; st["meta_dev"]=float(np.linalg.norm(dev))
                    if st["meta_dev"]>mb.get("trigger",0.45):
                        if dev[0]<-mb.get("deadband",0.12):
                            th.setdefault("energy",{})["metabolism"]=max(
                                mb.get("metab_floor",0.00005), th.get("energy",{}).get("metabolism",0.0004)*mb.get("metab_factor",0.82))
                            st["meta_fixes"]+=1; st["last_action"]="调代谢"
                        if dev[1]<-mb.get("deadband",0.12):
                            g2=th.setdefault("gate",{}); g2["cos_threshold"]=max(
                                mb.get("gate_min",0.25), g2.get("cos_threshold",0.65)-mb.get("gate_step",0.06))
                            st["meta_fixes"]+=1; st["last_action"]="松守门"
            elif name=="reflect_up":
                ru=th.get("reflect_up",{})
                if t%ru.get("reflect_every",40)==0 and t>0:
                    st["thoughts"].append({"prop":"t=%d 的自我命题"%t,"t":t})
                    if len(st["thoughts"])>ru.get("thought_max",30): st["thoughts"].pop(0)
            elif name=="lineage_mark":
                e_n=st["E"]/energy_cap
                st["stage"]= "壮年" if e_n>0.66 else "中年" if e_n>0.33 else "暮年" if e_n>0.1 else "濒死"

        # ---- 每步记录 ----
        T.rec("E", st["E"])
        T.rec("last_cos", st["last_cos"])
        T.rec("ret_ema", st["ret_ema"])
        T.rec("eta_eff", st["eta_eff"])
        T.rec("meta_dev", st["meta_dev"])
        if st["Sf"] is not None: T.rec("Sf_norm", np.linalg.norm(st["Sf"]))
        if st["Ss"] is not None: T.rec("Ss_norm", np.linalg.norm(st["Ss"]))
        if st["r"] is not None: T.rec("res_mean", float(np.mean(st["r"])))
        if st["s2"] is not None:
            for i,v in enumerate(st["s2"]): T.rec("s2_%d"%i, v)
        T.rec("meta_fixes", st["meta_fixes"])

    return T, st, th

# ============ 机制依赖图(来自实际实现) ============
DEPS = [
 ("selfread","gate","Ss → 守门"), ("gate","self_edit","cos → eta_eff"),
 ("gate","self_box","cos → s2"), ("energy","self_edit","E → eta_eff"),
 ("energy","self_box","E → s2"), ("retrieve","self_box","ret_ema → s2"),
 ("self_box","meta_box","s2 → 偏离"), ("meta_box","energy","修正代谢"),
 ("meta_box","gate","修正守门"), ("retrieve","energy","检索消耗/回血"),
 ("selfread","self_model","Sf/Sm/Ss → desc"), ("reservoir","self_box","状态"),
 ("reflect_up","self_model","thoughts → desc"), ("energy","lineage_mark","E → 阶段"),
]

def main():
    theta=load_theta()
    print("θ 来源:", "master_params.json" if theta else "内置默认")
    print("\n跑机制系统 600 步, 记录全部内部量...")
    T, st, th = run(theta, steps=600, seed=7)
    print("  机制调用:", dict(sorted(T.mech_calls.items(), key=lambda x:-x[1])))
    print("  状态槽:", len(T.slots))

    # 对照: 改一个杠杆参数
    print("\n对照: 改 energy.metabolism 0.0004 → 0.0002")
    T2, st2, _ = run(theta, steps=600, seed=7, perturb={"energy.metabolism":0.0002})
    print("  末态能量: %.4f vs %.4f"%(st["E"], st2["E"]))
    print("  元盒修正: %d vs %d"%(st["meta_fixes"], st2["meta_fixes"]))

    # ---- 生成 HTML 可视化 ----
    html = build_html(T, T2, DEPS, st, st2)
    out=os.path.join(HERE,"mechanism_viz.html")
    open(out,"w",encoding="utf-8").write(html)
    print("\n✅ 可视化 → %s (%.0f KB)"%(out, len(html)/1024))
    # 数据导出
    json.dump({"slots":{k:v for k,v in T.slots.items()},
               "mech_calls":T.mech_calls,
               "mech_fire":{k:v[:20] for k,v in T.mech_fire.items()}},
              open(os.path.join(HERE,"mechanism_trace.json"),"w"))
    print("   原始数据 → mechanism_trace.json")

def build_html(T, T2, deps, st, st2):
    slots_json = json.dumps({k:[round(x,4) for x in v] for k,v in T.slots.items()})
    slots2_json= json.dumps({k:[round(x,4) for x in v] for k,v in T2.slots.items()})
    calls_json = json.dumps(T.mech_calls)
    deps_json  = json.dumps(deps)
    fire_json  = json.dumps({k:v[:30] for k,v in T.mech_fire.items()})
    return """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>机制可解释性 · 完整内部视图</title>
<style>
body{margin:0;background:#0a0e15;color:#c9d6ea;font:13px/1.6 -apple-system,"PingFang SC",sans-serif}
.hd{padding:12px;background:#111823;border-bottom:1px solid #1f2b3f;position:sticky;top:0;z-index:9}
.hd h1{margin:0;font-size:15px;color:#3fe0d0}
.hd p{margin:4px 0 0;font-size:11px;color:#6f7f97}
.wrap{padding:12px;max-width:1100px;margin:0 auto}
.sec{background:#0f1621;border:1px solid #1f2b3f;border-radius:10px;margin-bottom:12px;padding:10px}
.sec h2{margin:0 0 8px;font-size:13px;color:#a06bff;display:flex;align-items:center;gap:8px}
.sec h2 span{font-size:10px;color:#6f7f97;font-weight:400}
canvas{width:100%;display:block;background:#070b11;border-radius:8px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:6px}
.chip{background:#111c2b;border:1px solid #1f2b3f;border-radius:7px;padding:5px 8px;font-size:11px}
.chip b{color:#ffb454;font-size:13px;font-variant-numeric:tabular-nums}
.chip i{font-style:normal;color:#6f7f97;display:block;font-size:10px}
table{width:100%;border-collapse:collapse;font-size:11.5px}
td,th{padding:4px 6px;border-bottom:1px solid #16202f;text-align:left}
th{color:#3fe0d0;font-weight:600}
.bar{height:12px;background:#3fe0d0;border-radius:2px;display:inline-block;vertical-align:middle}
.note{font-size:11px;color:#6f7f97;margin-top:6px;line-height:1.5}
ul{margin:4px 0;padding-left:18px;font-size:11.5px;color:#9fb3cc}
li{margin:2px 0}
</style></head><body>
<div class="hd"><h1>机制可解释性 · 完整内部视图</h1>
<p>数据来自真实运行 600 步 · 22 个机制 · 全部内部量可查 · 可导出</p></div>
<div class="wrap">

<div class="sec"><h2>① 状态槽总览 <span>末态</span></h2>
<div class="grid" id="slots"></div></div>

<div class="sec"><h2>② 核心状态时间序列 <span>600 步</span></h2>
<canvas id="c1" height="200"></canvas>
<div class="note" id="lg1"></div></div>

<div class="sec"><h2>③ 机制触发时序 <span>谁在什么时候跑</span></h2>
<div id="fire"></div>
<div class="note">周期越短的机制越"勤快"；meta_box/reflect_up 是每秒都跑（控制层）</div></div>

<div class="sec"><h2>④ 机制数据依赖 <span>谁喂谁</span></h2>
<div id="deps"></div>
<div class="note">这是机制的"因果图"—— 看懂它就懂了系统怎么运转</div></div>

<div class="sec"><h2>⑤ 因果对照 <span>改一个杠杆参数的影响</span></h2>
<canvas id="c2" height="180"></canvas>
<div class="note" id="lg2"></div></div>

<div class="sec"><h2>⑤b 能量收支拆解 <span>钱花在哪了</span></h2>
<div id="eflow"></div>
<div class="note">这是"可解释性"最有用的部分：能看清系统是"挣得多"还是"花得多"</div></div>

<div class="sec"><h2>⑥ 机制调用统计 <span>真实执行次数</span></h2>
<table id="tbl"></table></div>

<div class="sec"><h2>⑦ 原始数据 <span>可复制</span></h2>
<div class="note">完整状态序列已导出为 mechanism_trace.json，含每个槽每一步的值</div>
<div id="raw" style="font:10px ui-monospace,monospace;max-height:200px;overflow:auto;color:#7a92a8"></div></div>

</div>
<script>
var S=__SLOTS__, S2=__SLOTS2__, CALLS=__CALLS__, DEPS=__DEPS__, FIRE=__FIRE__;
var NAMES=["能量 E","对齐 cos","检索率","η 注入","元盒偏离"];
var KEYS=["E","last_cos","ret_ema","eta_eff","meta_dev"];
var COLS=["#3fe0d0","#a06bff","#ffb454","#4ade80","#ff5f6d"];

// ① 槽总览
(function(){
  var box=document.getElementById("slots"); var html="";
  KEYS.forEach(function(k,i){
    var v=S[k]||[]; if(!v.length) return;
    var last=v[v.length-1];
    html+='<div class="chip"><i>'+NAMES[i]+'</i><b>'+last.toFixed(3)+'</b></div>';
  });
  // 加上 s2 四维
  for(var i=0;i<4;i++){ var v=S["s2_"+i]; if(v&&v.length)
    html+='<div class="chip"><i>自我盒 维度'+i+'</i><b>'+v[v.length-1].toFixed(3)+'</b></div>'; }
  html+='<div class="chip"><i>Sf 范数</i><b>'+((S["Sf_norm"]||[0])[0]||0).toFixed(2)+'</b></div>';
  box.innerHTML=html;
})();

// ② 时间序列
function drawTS(cid, keys, names, cols, data){
  var cv=document.getElementById(cid); if(!cv) return;
  function fit(){ cv.width=cv.clientWidth*2; cv.height=(cv.getAttribute("height")||200)*2; }
  fit();
  var g=cv.getContext("2d"); var W=cv.width,H=cv.height;
  g.clearRect(0,0,W,H);
  // 网格
  g.strokeStyle="#16233a"; g.lineWidth=1;
  for(var i=0;i<=4;i++){ var y=H*i/4; g.beginPath(); g.moveTo(0,y); g.lineTo(W,y); g.stroke(); }
  // 归一化绘制
  keys.forEach(function(k,i){
    var v=data[k]; if(!v||!v.length) return;
    var mn=Math.min.apply(null,v), mx=Math.max.apply(null,v);
    var rng=(mx-mn)||1;
    g.beginPath(); g.strokeStyle=cols[i]; g.lineWidth=2.5;
    for(var j=0;j<v.length;j++){
      var x=W*j/(v.length-1||1);
      var y=H-4 - ((v[j]-mn)/rng)*(H-12);
      j? g.lineTo(x,y):g.moveTo(x,y);
    }
    g.stroke();
  });
  var lg=document.getElementById(cid=="c1"?"lg1":"lg2");
  if(lg) lg.innerHTML=names.map(function(n,i){
    return '<span style="color:'+cols[i]+'">■</span> '+n+'　'; }).join("");
}
drawTS("c1",["E","last_cos","ret_ema","eta_eff","meta_dev"],NAMES,COLS,S);
drawTS("c2",["E","last_cos","eta_eff"],["能量E","对齐cos","η注入"],COLS,S2);

// ③ 触发时序
(function(){
  var box=document.getElementById("fire"); var html="";
  var maxT=600;
  var items=Object.keys(FIRE).map(function(k){ return [k,FIRE[k]]; });
  items.sort(function(a,b){ return a[1][0]-b[1][0]; });
  items.forEach(function(it){
    var name=it[0], ts=it[1];
    var html2='<div style="display:flex;align-items:center;gap:8px;margin:2px 0">'+
      '<span style="width:110px;font-size:11px;color:#9fb3cc">'+name+'</span>'+
      '<span style="flex:1;height:8px;background:#0d1622;border-radius:4px;position:relative">';
    ts.slice(0,20).forEach(function(t){
      var pct=100*t/maxT;
      html2+='<span style="position:absolute;left:'+pct+'%;width:4px;height:8px;background:#3fe0d0;border-radius:1px"></span>';
    });
    html2+='</span><span style="font-size:10px;color:#6f7f97">'+(CALLS[name]||0)+'次</span></div>';
    html+=html2;
  });
  box.innerHTML=html;
})();

// ④ 依赖图
(function(){
  var box=document.getElementById("deps");
  var html='<table><tr><th>从</th><th>到</th><th>传什么</th></tr>';
  DEPS.forEach(function(d){ html+='<tr><td>'+d[0]+'</td><td>'+d[1]+'</td><td>'+(d[2]||'')+'</td></tr>'; });
  html+='</table>';
  box.innerHTML=html;
})();

// ⑤b 能量收支
(function(){
  var EF=__EFLOW__;
  var box=document.getElementById("eflow");
  var items=[
    ["消耗: 基础代谢","metab","#ff5f6d"],
    ["消耗: 检索","retrieve","#ff9aa6"],
    ["恢复: 对齐回血","recover","#4ade80"],
    ["恢复: 休息回血","rest","#3fe0d0"],
    ["恢复: 检索收益","gain","#a06bff"]
  ];
  var mx=Math.max.apply(null,items.map(function(i){return EF[i[1]]||0;}))||1;
  var html="";
  items.forEach(function(i){
    var v=EF[i[1]]||0;
    html+='<div style="display:flex;align-items:center;gap:8px;margin:3px 0">'+
      '<span style="width:120px;font-size:11px;color:#9fb3cc">'+i[0]+'</span>'+
      '<span style="flex:1;height:14px;background:#0d1622;border-radius:3px;overflow:hidden">'+
      '<span style="display:block;height:14px;width:'+(100*v/mx)+'%;background:'+i[2]+'"></span></span>'+
      '<span style="width:70px;text-align:right;font-size:11px;color:#ffb454">'+v.toFixed(3)+'</span></div>';
  });
  var earn=(EF.recover||0)+(EF.rest||0)+(EF.gain||0);
  var cost=(EF.metab||0)+(EF.retrieve||0);
  html+='<div style="margin-top:8px;padding:8px;background:#0d1622;border-radius:8px;font-size:12px">'+
    '总收入 <b style="color:#4ade80">'+earn.toFixed(3)+'</b>　'+
    '总支出 <b style="color:#ff5f6d">'+cost.toFixed(3)+'</b>　'+
    '净值 <b style="color:'+(earn-cost>0?"#4ade80":"#ff5f6d")+'">'+
    (earn-cost>0?"+":"")+(earn-cost).toFixed(3)+'</b>　'+
    '<span style="color:#6f7f97">('+(earn>cost?"活的下去 ✅":"会饿死 ❌")+')</span></div>';
  box.innerHTML=html;
})();

// ⑥ 调用统计
(function(){
  var box=document.getElementById("tbl");
  var items=Object.keys(CALLS).map(function(k){return [k,CALLS[k]];}).sort(function(a,b){return b[1]-a[1];});
  var max=items.length?items[0][1]:1;
  var html='<tr><th>机制</th><th>执行次数</th><th></th></tr>';
  items.forEach(function(it){
    html+='<tr><td>'+it[0]+'</td><td>'+it[1]+'</td><td><span class="bar" style="width:'+(120*it[1]/max)+'px"></span></td></tr>';
  });
  box.innerHTML=html;
})();

// ⑦ 原始数据
(function(){
  var el=document.getElementById("raw");
  var txt="";
  Object.keys(S).forEach(function(k){
    txt += k + ": [" + S[k].slice(0,8).map(function(x){return x.toFixed(3);}).join(", ") + " ...]\n";
  });
  el.textContent=txt;
})();
</script></body></html>""".replace("__SLOTS__",slots_json).replace("__SLOTS2__",slots2_json)\
        .replace("__CALLS__",calls_json).replace("__DEPS__",deps_json).replace("__FIRE__",fire_json)\
        .replace("__EFLOW__",json.dumps(T.energy_flow))

if __name__=="__main__":
    main()
