"""
巨构场景生成器 V2 — 现代化UI (Canvas圆角+渐变+交互)
"""
import os, json, requests, base64, time, threading, re, glob
from datetime import datetime
from tkinter import *
from tkinter import ttk, messagebox, filedialog
from io import BytesIO
import math

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR,"config.json")
STYLES_DIR = os.path.join(BASE_DIR,"styles")
OUTPUT_BASE = os.path.join(BASE_DIR,"output")
os.makedirs(STYLES_DIR,exist_ok=True); os.makedirs(OUTPUT_BASE,exist_ok=True)
VERSION="V2.0"

# ====== Palette ======
C={
 "bg":"#111218","card":"#1a1c25","surf":"#22243a","input":"#282a3a",
 "accent":"#6c5ce7","accent2":"#00cec9","warn":"#e17055",
 "text":"#dfe6e9","body":"#b2bec3","hint":"#636e72","border":"#2d3045"
}
R=10

# Fonts
F_H1=("Segoe UI",14,"bold"); F_H2=("Segoe UI",12,"bold")
F_LBL=("Segoe UI",11); F_BTN=("Segoe UI",11,"bold")
F_IN=("Segoe UI",12); F_SM=("Segoe UI",10)

DEFAULT_CONFIG={
 "llm_api_key":"","llm_base_url":"https://api.apimart.ai/v1","text_model":"deepseek-v4-flash",
 "image_api_key":"","image_base_url":"https://api.apimart.ai/v1","image_model":"gpt-image-2-official",
 "api_provider":"apimart","api_mode":"async","poll_interval":2000,"max_polls":60,
 "keep_human":True,"selected_style":"太古遗迹巨构",
 "auto_switch_style":False,"auto_rotate":True,
 "random_composition":False,"random_lighting":False,"custom_suffix":""
}
def load_config():
 if os.path.exists(CONFIG_FILE):
  with open(CONFIG_FILE,"r",encoding="utf-8") as f: cfg=json.load(f)
  for k in DEFAULT_CONFIG: cfg.setdefault(k,DEFAULT_CONFIG[k])
  return cfg
 return dict(DEFAULT_CONFIG)
def save_config(cfg):
 with open(CONFIG_FILE,"w",encoding="utf-8") as f: json.dump(cfg,f,ensure_ascii=False,indent=2)
def sanitize(s): return re.sub(r'[\\/:*?"<>|]','_',s)[:40]
def load_styles():
 st={}
 if os.path.isdir(STYLES_DIR):
  for fp in sorted(glob.glob(os.path.join(STYLES_DIR,"*.json"))):
   try:
    with open(fp,"r",encoding="utf-8") as f: d=json.load(f)
    n=d.get("style_name","")
    if n: d.setdefault("bgm_keywords","");d.setdefault("art_style","");d.setdefault("image_api_config",{"save_path":"./output/"});st[n]=d
   except: pass
 return st
ALL_STYLES=load_styles(); STYLE_NAMES=list(ALL_STYLES.keys()); _RI=0
def get_style(n): return ALL_STYLES.get(n,list(ALL_STYLES.values())[0] if ALL_STYLES else {})
def next_hint(): global _RI;_RI+=1;return STYLE_NAMES[(_RI-1)%len(STYLE_NAMES)] if STYLE_NAMES else ""

# ====== Canvas drawing ======
def rr(cv,x1,y1,x2,y2,r,**kw):
 pts=[x1+r,y1,x2-r,y1,x2,y1,x2,y1+r,x2,y2-r,x2,y2,x2-r,y2,x1+r,y2,x1,y2,x1,y2-r,x1,y1+r,x1,y1,x1+r,y1]
 return cv.create_polygon(pts,smooth=True,**kw)
 
def gradient(cv,w,h,c1,c2):
 """Draw vertical gradient"""
 for i in range(h):
  r1,g1,b1=int(c1[1:3],16),int(c1[3:5],16),int(c1[5:7],16)
  r2,g2,b2=int(c2[1:3],16),int(c2[3:5],16),int(c2[5:7],16)
  ratio=i/h
  r=int(r1*(1-ratio)+r2*ratio);g=int(g1*(1-ratio)+g2*ratio);b=int(b1*(1-ratio)+b2*ratio)
  color=f"#{r:02x}{g:02x}{b:02x}"
  cv.create_line(0,i,w,i,fill=color)

# ====== Custom Widgets ======
class Card(Frame):
 """Canvas rounded card with optional gradient header"""
 def __init__(self,parent,title="",hdr_gradient=False,**kw):
  super().__init__(parent,bg=C["bg"],**kw)
  self.title=title; self.hdr_grad=hdr_gradient; self.inner=None
  self.bind("<Configure>",self._draw)
 def _draw(self,e=None):
  for w in self.winfo_children():
   if isinstance(w,Canvas): w.destroy(); break
  w=self.winfo_width(); h=self.winfo_height()
  if w<10: return
  cv=Canvas(self,bg=C["bg"],highlightthickness=0,bd=0,width=w,height=h)
  cv.place(x=0,y=0)
  # Shadow
  rr(cv,3,3,w-3,h-3,R,fill="#00000022",outline="")
  # Card body
  rr(cv,0,0,w-2,h-2,R,fill=C["card"],outline=C["border"],width=1)
  # Gradient header
  if self.title and self.hdr_grad:
   _h=38
   rr(cv,0,0,w-2,_h,R,fill=C["accent"],outline="",tags="hdr")
   cv.create_rectangle(0,_h//2,w-2,_h,fill=C["accent"],outline="")
   cv.create_text(w//2,_h//2,text=self.title,font=F_H2,fill="#fff")
  elif self.title:
   cv.create_text(14,14,text=self.title,font=F_H2,fill=C["text"],anchor="w")
  self.inner=cv

class GBtn(Frame):
 """Gradient button with hover"""
 def __init__(self,parent,text,cmd=None,accent=True,small=False):
  super().__init__(parent,bg=C["bg"])
  self.text=text; self.cmd=cmd; self.accent=accent; self.small=small
  self._state=NORMAL
  self.bind("<Configure>",self._draw)
  self.bind("<Enter>",self._on_enter)
  self.bind("<Leave>",self._on_leave)
  self.bind("<Button-1>",self._on_click)
  self["cursor"]="hand2"
  self.pw=80 if not small else 60; self.ph=32 if not small else 26
  self.config(width=self.pw,height=self.ph)
 def _draw(self,e=None):
  for w in self.winfo_children(): 
   if isinstance(w,Canvas): w.destroy(); break
  w=self.winfo_width() or self.pw; h=self.winfo_height() or self.ph
  cv=Canvas(self,bg=C["bg"],highlightthickness=0,bd=0,width=w,height=h)
  cv.pack(fill=BOTH,expand=True)
  self.cv=cv
  if self.accent:
   gradient(cv,w,h,"#6c5ce7","#a29bfe")
  else:
   rr(cv,0,0,w,h,R,fill=C["surf"],outline=C["border"],width=1)
  rr(cv,0,0,w-1,h-1,R,fill="" if self.accent else C["surf"],outline="",tags="bg")
  if self.accent:
   gradient(cv,w,h,"#6c5ce7","#a29bfe")
   rr(cv,0,0,w-1,h-1,R,fill="",outline="",tags="bg")
  fs=F_BTN if not self.small else F_LBL
  cv.create_text(w//2,h//2,text=self.text,font=fs,fill="#fff")
 def _on_enter(self,e):
  if hasattr(self,'cv'): 
   if self.accent: self.cv.delete("bg");gradient(self.cv,self.cv.winfo_width(),self.cv.winfo_height(),"#7c6cf7","#b4aaff")
   else: rr(self.cv,0,0,self.cv.winfo_width()-1,self.cv.winfo_height()-1,R,fill="#2d3045",outline=C["accent"],width=1)
  self["cursor"]="hand2"
 def _on_leave(self,e):
  if hasattr(self,'cv'):self._draw(None)
 def _on_click(self,e):
  if self._state==NORMAL and self.cmd: self.cmd()

class GIBox(Frame):
 """Entry with rounded frame"""
 def __init__(self,parent,var=None,w=None,show=None):
  super().__init__(parent,bg=C["bg"])
  self.var=var or StringVar()
  self.bind("<Configure>",self._draw)
  self.en=Entry(self,textvariable=self.var,font=F_IN,bg=C["input"],fg=C["text"],
                relief=FLAT,bd=0,insertbackground=C["text"],show=show or "",
                highlightthickness=0,width=w)
  self.en.pack(fill=BOTH,expand=True,padx=8,pady=6)
 def _draw(self,e=None):
  pass  # Simply styled via entry itself

class GText(Frame):
 def __init__(self,parent,height=3):
  super().__init__(parent,bg=C["bg"])
  self.bind("<Configure>",self._draw)
  self.tx=Text(self,wrap=WORD,font=F_IN,bg=C["input"],fg=C["body"],
               relief=FLAT,bd=0,padx=8,pady=6,highlightthickness=0)
  self.tx.pack(fill=BOTH,expand=True,padx=1,pady=1)
 def _draw(self,e=None):
  pass

def Label_(p,t,c=C["hint"],s=11):
 return Label(p,text=t,font=("Segoe UI",s),bg=C["card"],fg=c)

# ====== Toast ======
class Toast:
 @staticmethod
 def show(parent,msg,color=C["accent2"],dur=1800):
  tl=Toplevel(parent); tl.overrideredirect(True); tl.attributes("-topmost",True)
  x=parent.winfo_rootx()+parent.winfo_width()//2-100; y=parent.winfo_rooty()+60
  tl.geometry(f"220x38+{x}+{y}")
  cv=Canvas(tl,bg=color,highlightthickness=0,width=220,height=38)
  cv.pack()
  rr(cv,0,0,220,38,8,fill=color,outline="")
  cv.create_text(110,19,text=msg,font=F_LBL,fill="#fff")
  tl.after(dur,tl.destroy)

# ====== Main App ======
class App:
 def __init__(self,root):
  self.root=root; self.root.configure(bg=C["bg"])
  self.config=load_config()
  self.style_name=self.config.get("selected_style","")
  if self.style_name not in STYLE_NAMES and STYLE_NAMES: self.style_name=STYLE_NAMES[0]
  self.STYLE=get_style(self.style_name)
  self.subject=""; self.full_prompt=""; self.b64_result=None; self._busy=False; self._batch_stop=False
  self._build()
 def opath(self):
  sp=self.STYLE.get("image_api_config",{}).get("save_path","./output/")
  return os.path.join(BASE_DIR,sp.replace("./",""))

 def _build(self):
  self.root.title("巨构场景生成器 V2"); self.root.geometry("1140x780"); self.root.minsize(960,660)
  
  # ====== Title Bar ======
  tb=Canvas(self.root,bg="#0d0e14",highlightthickness=0,bd=0,height=40)
  tb.pack(fill=X)
  tb.create_text(18,20,text="巨构场景生成器",font=("Segoe UI",13,"bold"),fill=C["text"],anchor="w")
  tb.create_text(200,20,text=VERSION,font=F_SM,fill=C["hint"],anchor="w")
  Button(tb,text="✕",font=("Segoe UI",12),bg="#0d0e14",fg=C["hint"],relief=FLAT,bd=0,
         padx=12,activebackground="#e17055",activeforeground="white",command=self.root.destroy).place(x=1100,y=6)
  
  # ====== Main area ======
  mc=Frame(self.root,bg=C["bg"]); mc.pack(fill=BOTH,expand=True,padx=16,pady=10)
  
  # ---- Top bar ----
  bar=Frame(mc,bg=C["bg"]); bar.pack(fill=X,pady=(0,12))
  self.sv=StringVar(value=self.style_name)
  cb=ttk.Combobox(bar,textvariable=self.sv,values=STYLE_NAMES,state="readonly",width=24)
  cb.pack(side=LEFT)
  cb.bind("<<ComboboxSelected>>",self._os)
  self.arv=BooleanVar(value=self.config.get("auto_rotate",True))
  Checkbutton(bar,text="自动轮换",variable=self.arv,font=F_LBL,bg=C["bg"],fg=C["body"],
               selectcolor=C["input"],activebackground=C["bg"]).pack(side=LEFT,padx=(10,0))
  self.sb=GBtn(bar,"批量生成",self._batch,accent=False,small=True)
  self.sb.pack(side=RIGHT,padx=(0,6))
  GBtn(bar,"设置",self._settings,accent=False,small=True).pack(side=RIGHT,padx=(0,6))

  # ---- Body ----
  bd=Frame(mc,bg=C["bg"]); bd.pack(fill=BOTH,expand=True)
  
  # LEFT
  lt=Frame(bd,bg=C["bg"]); lt.pack(side=LEFT,fill=BOTH,expand=True,padx=(0,12))
  
  # Card 1: Input
  c1=Frame(lt,bg=C["card"]); c1.pack(fill=X,pady=(0,12))
  Label(c1,text="画面描述",font=F_H2,bg=C["card"],fg=C["text"]).pack(anchor=W,padx=14,pady=(10,0))
  sr=Frame(c1,bg=C["card"]); sr.pack(fill=X,padx=14,pady=(6,12))
  self.iv=StringVar()
  GIBox(sr,self.iv).pack(side=LEFT,fill=X,expand=True,padx=(0,8))
  GBtn(sr,"刷新灵感",self._refresh,accent=False,small=True).pack(side=LEFT,padx=(0,4))
  GBtn(sr,"开始生成",self._gen,accent=True,small=True).pack(side=LEFT)

  # Card 2: Preview
  c2=Frame(lt,bg=C["card"]); c2.pack(fill=BOTH,expand=True,pady=(0,12))
  Label(c2,text="图像预览",font=F_H2,bg=C["card"],fg=C["text"]).pack(anchor=W,padx=14,pady=(10,0))
  pf=Frame(c2,bg=C["input"],height=260,highlightbackground=C["border"],highlightthickness=1)
  pf.pack(fill=BOTH,expand=True,padx=14,pady=(6,6))
  pf.pack_propagate(False)
  self.pvl=Label(pf,text="等待生成",font=F_LBL,bg=C["input"],fg=C["hint"])
  self.pvl.pack(expand=True)
  br=Frame(c2,bg=C["card"]); br.pack(fill=X,padx=14,pady=(0,10))
  for t,c in [("💾 另存",self._sa),("📁 打开目录",self._od),("📄 导出文档",self._ex)]:
   GBtn(br,t,c,accent=False,small=True).pack(side=LEFT,padx=(0,6))

  # Status
  st=Frame(mc,bg=C["surf"])
  st.pack(fill=X,pady=(0,0))
  self.stat=Label(st,text="就绪",font=F_SM,bg=C["surf"],fg=C["hint"])
  self.stat.pack(side=LEFT,padx=12,pady=5)
  self.prog=ttk.Progressbar(st,mode="indeterminate",length=60)
  self.prog.pack(side=LEFT,padx=(6,0))
  self.hnt=Label(st,text="",font=F_SM,bg=C["surf"],fg=C["accent2"])
  self.hnt.pack(side=LEFT,padx=(8,0))

  # RIGHT
  rt=Frame(bd,bg=C["bg"],width=300); rt.pack(side=RIGHT,fill=Y); rt.pack_propagate(False)
  
  # Card R1: Controls
  r1=Frame(rt,bg=C["card"]); r1.pack(fill=X,pady=(0,10))
  Label(r1,text="画面控制",font=F_H2,bg=C["card"],fg=C["text"]).pack(anchor=W,padx=12,pady=(8,0))
  rg=Frame(r1,bg=C["card"]); rg.pack(fill=X,padx=12,pady=(4,8))
  self.rcv=BooleanVar(value=False)
  Checkbutton(rg,text="构图扰动",variable=self.rcv,font=F_LBL,bg=C["card"],
               fg=C["body"],selectcolor=C["input"],activebackground=C["card"]).pack(side=LEFT,padx=(0,10))
  self.rlv=BooleanVar(value=False)
  Checkbutton(rg,text="光影微调",variable=self.rlv,font=F_LBL,bg=C["card"],
               fg=C["body"],selectcolor=C["input"],activebackground=C["card"]).pack(side=LEFT)

  # Card R2: Caption
  r2=Frame(rt,bg=C["card"]); r2.pack(fill=X,pady=(0,10))
  Label(r2,text="文案素材",font=F_H2,bg=C["card"],fg=C["text"]).pack(anchor=W,padx=12,pady=(8,0))
  cg=Frame(r2,bg=C["card"]); cg.pack(fill=X,padx=12,pady=(4,8))
  Label_(cg,"短视频文案",C["hint"],10).pack(anchor=W)
  self.ct=GText(cg,3); self.ct.pack(fill=X,pady=(2,4))
  self.ct.tx.insert("1.0",self.STYLE.get("captions",{}).get("medium",""))
  Label_(cg,"生图描述词",C["hint"],10).pack(anchor=W)
  self.be=GIBox(cg); self.be.pack(fill=X,pady=(2,4))
  self.be.en.insert(0,self.STYLE.get("bgm_keywords",""))
  for t,c in [("📋 复制文案",self._cc),("🖼 复制描述词",self._cb)]:
   GBtn(cg,t,c,accent=False,small=True).pack(side=LEFT,padx=(0,4))

  # Card R3: Prompt
  r3=Frame(rt,bg=C["card"]); r3.pack(fill=X,pady=(0,10))
  Label(r3,text="生成参数",font=F_H2,bg=C["card"],fg=C["text"]).pack(anchor=W,padx=12,pady=(8,0))
  pg=Frame(r3,bg=C["card"]); pg.pack(fill=X,padx=12,pady=(4,8))
  Label_(pg,"当前主体",C["hint"],10).pack(anchor=W)
  self.sd=Label(pg,text="（尚未生成）",font=F_IN,bg=C["input"],fg=C["hint"],
                 anchor=W,padx=8,pady=4)
  self.sd.pack(fill=X,pady=2)
  Label_(pg,"完整提示词",C["hint"],10).pack(anchor=W)
  self.pt=GText(pg,4); self.pt.pack(fill=X,pady=2)
  self.pt.tx.insert("1.0","生成后自动填充")
  GBtn(pg,"📋 复制提示词",self._cp,accent=False,small=True).pack(anchor=W)

  # Bottom
  bm=Frame(self.root,bg="#0d0e14",height=22); bm.pack(fill=X)
  Label(bm,text=f"输出: {self.opath()}  |  {VERSION}",font=F_SM,bg="#0d0e14",fg=C["hint"]).pack(side=LEFT,padx=10)

 # ====== Events ======
 def _st(self,m,c=C["hint"]): self.stat.config(text=m,fg=c); self.root.update()
 def _bs(self,b):
  s=NORMAL if not b else DISABLED; self.sb._state=s
  if b: self.prog.start(10)
  else: self.prog.stop()
  self.root.update()
 def _clip(self,t): self.root.clipboard_clear();self.root.clipboard_append(t);Toast.show(self.root,"已复制")
 def _os(self,e=None):
  n=self.sv.get();self.config["selected_style"]=n;save_config(self.config);self.STYLE=get_style(n)
  self.ct.tx.delete("1.0",END);self.ct.tx.insert("1.0",self.STYLE.get("captions",{}).get("medium",""))
  self.be.en.delete(0,END);self.be.en.insert(0,self.STYLE.get("bgm_keywords",""))
  Toast.show(self.root,f"已切换: {n}")
 def _bp(self,s):
  bp=self.STYLE.get("base_positive","");art=self.STYLE.get("art_style","")
  p=f"{s}, {art}, {bp}" if art else f"{s}, {bp}"
  sfx=self.config.get("custom_suffix","")
  if sfx: p+=f", {sfx}"
  return p

 # ====== Settings ======
 def _settings(self):
  d=Toplevel(self.root);d.title("设置");d.geometry("480x580");d.configure(bg=C["bg"])
  d.transient(self.root);d.grab_set()
  cv=Canvas(d,bg=C["card"],highlightthickness=0,width=452,height=548)
  cv.pack(padx=14,pady=14)
  rr(cv,0,0,452,548,R,fill=C["card"],outline="")
  cv.create_text(20,20,text="设置",font=F_H1,fill=C["text"],anchor="w")
  vars={}
  y0=55
  def sec(t,items):
   nonlocal y0
   cv.create_text(20,y0,text=t,font=("Segoe UI",10,"bold"),fill=C["accent2"],anchor="w");y0+=24
   for l,k,sh,opts in items:
    cv.create_text(20,y0,text=l,font=F_SM,fill=C["hint"],anchor="w");y0+=18
    if opts:
     v=StringVar(value=str(self.config.get(k,"")));
     cb2=ttk.Combobox(d,textvariable=v,state="readonly",values=opts);cb2.place(x=20,y=y0,width=412);y0+=32
    elif sh:
     v=StringVar(value=str(self.config.get(k,"")));
     en=Entry(d,textvariable=v,show="*",font=F_IN,bg=C["input"],fg=C["text"],relief=FLAT,bd=0);en.place(x=20,y=y0,width=412);y0+=32
    else:
     v=StringVar(value=str(self.config.get(k,"")));
     en=Entry(d,textvariable=v,font=F_IN,bg=C["input"],fg=C["text"],relief=FLAT,bd=0);en.place(x=20,y=y0,width=412);y0+=32
    vars[k]=v
  sec("LLM（写灵感）",[
   ("API Key","llm_api_key",True,None),("Base URL","llm_base_url",False,None),
   ("模型","text_model",False,["deepseek-v4-flash","deepseek-chat","gpt-4o-mini","gpt-4o","gpt-5"])])
  sec("出图（画图）",[
   ("API Key","image_api_key",True,None),("Base URL","image_base_url",False,None),
   ("模型","image_model",False,["gpt-image-2-official","gpt-image-2-ext","dall-e-3"])])
  cv.create_text(20,y0,text="自定义后缀 Prompt",font=F_SM,fill=C["hint"],anchor="w");y0+=18
  cv_=StringVar(value=self.config.get("custom_suffix",""))
  en=Entry(d,textvariable=cv_,font=F_IN,bg=C["input"],fg=C["text"],relief=FLAT,bd=0)
  en.place(x=20,y=y0,width=412);y0+=40
  def save():
   for k,v in vars.items():self.config[k]=v.get().strip()
   self.config["custom_suffix"]=cv_.get().strip();save_config(self.config);d.destroy();Toast.show(self.root,"已保存")
  GBtn(Canvas(d,bg=C["card"],highlightthickness=0,width=100,height=32), "保存",save,accent=True).place(x=340,y=y0)

 # ====== API ======
 def _lh(self):
  k=self.config.get("llm_api_key","")
  if not k:raise ValueError("缺少 LLM Key")
  return {"Authorization":f"Bearer {k}","Content-Type":"application/json"}
 def _ih(self):
  k=self.config.get("image_api_key","")
  if not k:raise ValueError("缺少 出图 Key")
  return {"Authorization":f"Bearer {k}","Content-Type":"application/json"}
 def _gs(self,sn):
  s=get_style(sn);gp=s.get("dynamic_subject_generate_prompt","") or "生成主体。"
  h=self._lh()
  p={"model":self.config.get("text_model","deepseek-v4-flash"),
     "messages":[{"role":"user","content":gp}],"max_tokens":80,"temperature":0.9}
  r=requests.post(f"{self.config.get('llm_base_url','https://api.apimart.ai/v1')}/chat/completions",headers=h,json=p,timeout=30)
  r.raise_for_status()
  return r.json()["choices"][0]["message"]["content"].strip().strip("\"'")
 def _sub(self,prompt):
  h=self._ih()
  p={"model":self.config.get("image_model","gpt-image-2-official"),"prompt":prompt,"n":1,
     "size":"1792x1024","response_format":"b64_json"}
  r=requests.post(f"{self.config.get('image_base_url','https://api.apimart.ai/v1')}/images/generations",headers=h,json=p,timeout=30)
  return r.json().get("data",[{}])[0].get("task_id")
 def _poll(self,tid):
  base=self.config.get("image_base_url","https://api.apimart.ai/v1");h=self._ih()
  mx=self.config.get("max_polls",60)
  for i in range(mx):
   self._st(f"生成中 {i+1}/{mx}...")
   try:
    r=requests.get(f"{base}/tasks/{tid}?language=zh",headers=h,timeout=30);d=r.json()
    st=d.get("data",{}).get("status","")
    if st=="completed":
     imgs=d.get("data",{}).get("result",{}).get("images",[])
     if imgs:
      u=imgs[0].get("url")
      if isinstance(u,list):u=u[0]
      rd=requests.get(u,timeout=30);return base64.b64encode(rd.content).decode()
     return None
    elif st in ("failed","cancelled"):return None
   except: pass
   time.sleep(self.config.get("poll_interval",2000)/1000)
  return None
 def _simg(self,b64,subj=None):
  ts=datetime.now().strftime("%Y%m%d_%H%M%S");fn=f"{ts}_{sanitize(subj or self.subject or 'untitled')}.png"
  fp=os.path.join(self.opath(),fn);os.makedirs(self.opath(),exist_ok=True)
  with open(fp,"wb") as f:f.write(base64.b64decode(b64));return fp
 def _sinfo(self,p,subj,pr,sn):
  base=os.path.splitext(p)[0];cap=self.STYLE.get("captions",{}).get("medium","")
  bgm=self.STYLE.get("bgm_keywords","")
  lines=[f"主体: {subj}","",f"提示词: {pr}","",f"风格: {sn}","",f"文案: {cap}","",f"BGM: {bgm}"]
  with open(base+".txt","w",encoding="utf-8") as f:f.write("\n".join(lines))
 def _pvw(self,b64):
  try:
   from PIL import Image,ImageTk
   bio=BytesIO(base64.b64decode(b64));img=Image.open(bio)
   img.thumbnail((620,240),Image.LANCZOS);tk=ImageTk.PhotoImage(img)
   self.pvl.config(image=tk,text="",bg=C["input"]);self.pvl.image=tk
  except:self.pvl.config(text="已保存",bg=C["input"],fg=C["hint"])

 # ====== Actions ======
 def _refresh(self):
  if not self.config.get("llm_api_key"):return Toast.show(self.root,"请设置 LLM API Key",C["warn"])
  u=self.iv.get().strip()
  if u and not messagebox.askyesno("确认","覆盖已有内容？"):return
  threading.Thread(target=self._dr,daemon=True).start()
 def _dr(self):
  self._bs(True);self._st("生成灵感...",C["accent"])
  try:
   ts=self.style_name
   if self.arv.get():
    h=next_hint()
    if h:ts=h
   s=self._gs(ts);self.subject=s
   if ts!=self.style_name:self.hnt.config(text=f"偏向「{ts}」")
   self.root.after(0,self._fs)
  except:Toast.show(self.root,"生成失败",C["warn"]);self._st("失败",C["warn"])
  finally:self._bs(False)
 def _fs(self):
  self.sd.config(text=self.subject,fg=C["text"])
  self.full_prompt=self._bp(self.subject)
  self.pt.tx.delete("1.0",END);self.pt.tx.insert("1.0",self.full_prompt)
  self._st("就绪",C["accent2"])
 def _gen(self):
  if not self.config.get("image_api_key"):return Toast.show(self.root,"请设置 出图 API Key",C["warn"])
  u=self.iv.get().strip()
  if u:self.subject=u;self._fs()
  elif not self.subject:return self._refresh()
  threading.Thread(target=self._dg,daemon=True).start()
 def _dg(self):
  self._bs(True);self._st("生成中...",C["accent"]);self.hnt.config(text="")
  try:
   tid=self._sub(self.full_prompt);b64=self._poll(tid) if tid else None
   if b64:
    self.b64_result=b64;p=self._simg(b64);self._sinfo(p,self.subject,self.full_prompt,self.style_name)
    self.root.after(0,lambda:self._pvw(b64));self._clip(self.full_prompt)
    self._st("完成",C["accent2"])
   else:Toast.show(self.root,"超时或失败",C["warn"]);self._st("失败",C["warn"])
  except:Toast.show(self.root,"失败",C["warn"]);self._st("失败",C["warn"])
  finally:self._bs(False)
 def _batch(self):
  if not self.config.get("llm_api_key"):return Toast.show(self.root,"请设置 API Key",C["warn"])
  d=Toplevel(self.root);d.title("批量");d.geometry("300x180");d.configure(bg=C["bg"])
  d.transient(self.root);d.grab_set()
  Label(d,text="数量 (1-20)",font=F_LBL,bg=C["bg"],fg=C["hint"]).pack(pady=(14,0))
  nv=StringVar(value="5")
  Entry(d,textvariable=nv,font=F_IN,bg=C["input"],fg=C["text"],relief=FLAT,bd=0,width=6).pack(pady=4)
  rv=BooleanVar(value=True)
  Checkbutton(d,text="自动轮换",variable=rv,font=F_LBL,bg=C["bg"],fg=C["body"],selectcolor=C["input"]).pack()
  def st():
   try:n=int(nv.get())
   except:n=5
   d.destroy();threading.Thread(target=self._db,args=(max(1,min(20,n)),rv.get()),daemon=True).start()
  GBtn(Canvas(d,bg=C["bg"],highlightthickness=0,width=80,height=32),"开始",st,accent=True).pack(pady=10)
 def _db(self,cnt,rot):
  self._batch_stop=False;self._bs(True);done=0
  sb=Button(self.root,text="■",bg=C["warn"],fg="white",font=F_BTN,relief=FLAT,bd=0,padx=6,pady=2,command=self._sbs)
  sb.place(x=620,y=10)
  try:
   for i in range(cnt):
    if self._batch_stop:break
    if rot:h=next_hint()
    if h and rot:self.sv.set(h);self._os()
    s=self._gs(self.style_name);self.subject=s;self.full_prompt=self._bp(s)
    self._st(f"批量 {i+1}/{cnt}...")
    tid=self._sub(self.full_prompt);b64=self._poll(tid) if tid else None
    if b64:p=self._simg(b64,s);self._sinfo(p,s,self.full_prompt,self.style_name);done+=1
    time.sleep(1.5)
  except:pass
  sb.destroy();self._bs(False);self._st(f"批量: {done}/{cnt}",C["accent2"]);Toast.show(self.root,f"完成 {done}/{cnt}")
 def _sbs(self):self._batch_stop=True
 def _sa(self):
  if not self.b64_result:return Toast.show(self.root,"无图片",C["warn"])
  fp=filedialog.asksaveasfilename(defaultextension=".png",filetypes=[("PNG","*.png")])
  if fp:open(fp,"wb").write(base64.b64decode(self.b64_result));Toast.show(self.root,"已保存")
 def _od(self):os.startfile(self.opath())
 def _ex(self):
  if not self.subject:return Toast.show(self.root,"无内容",C["warn"])
  ts=datetime.now().strftime("%Y%m%d_%H%M%S")
  fp=os.path.join(self.opath(),f"info_{ts}.txt")
  cap=self.STYLE.get("captions",{}).get("medium","");bgm=self.STYLE.get("bgm_keywords","")
  with open(fp,"w",encoding="utf-8") as f:f.write(f"主体: {self.subject}\n\n提示词: {self.full_prompt}\n\n文案: {cap}\n\nBGM: {bgm}")
  Toast.show(self.root,"已导出")
 def _cp(self):
  t=self.pt.tx.get("1.0",END).strip()
  if t and t not in ("生成后自动填充","风格已切换"):self._clip(t)
 def _cc(self):
  t=self.ct.tx.get("1.0",END).strip()
  if t:self._clip(t)
 def _cb(self):
  t=self.be.en.get()
  if t:self._clip(t)

def main():
 root=Tk();App(root);root.mainloop()
if __name__=="__main__":
 main()
