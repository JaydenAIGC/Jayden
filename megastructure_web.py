"""
街灯AI--场景生成器 — 底部控制栏布局
"""
import os, sys, json, requests, base64, time, threading, re, glob, http.server
from datetime import datetime
from urllib.parse import urlparse

# PyInstaller兼容：数据文件存EXE同目录，风格文件从打包目录读取
if getattr(sys,'frozen',False):
    BASE_DIR = os.path.dirname(sys.executable)
    STYLE_DIR = os.path.join(BASE_DIR, "styles")
    # 首次运行：把打包内的风格文件复制到EXE同目录
    if not os.path.exists(STYLE_DIR):
        import shutil
        src_styles = os.path.join(sys._MEIPASS, "styles")
        if os.path.exists(src_styles):
            shutil.copytree(src_styles, STYLE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    STYLE_DIR = os.path.join(BASE_DIR, "styles")

class Backend:
    def __init__(self):
        self.config = self._load_config()
        self.STYLES = self._load_styles()
        self.STYLE_NAMES = list(self.STYLES.keys())
        self.style_name = self.config.get("selected_style","")
        if self.style_name not in self.STYLE_NAMES and self.STYLE_NAMES:
            self.style_name = self.STYLE_NAMES[0]
        self.STYLE = self.STYLES.get(self.style_name, {})
    def _load_config(self):
        fp = os.path.join(BASE_DIR,"config.json")
        d = {"llm_api_key":"","llm_base_url":"https://api.apimart.ai/v1","text_model":"deepseek-v4-flash",
             "image_api_key":"","image_base_url":"https://api.apimart.ai/v1","image_model":"gpt-image-2-official",
             "poll_interval":2000,"max_polls":60,"selected_style":"太古遗迹巨构","custom_suffix":"","keep_human":True}
        if os.path.exists(fp):
            with open(fp,"r",encoding="utf-8") as f: c=json.load(f)
            for k in d: c.setdefault(k,d[k])
        else:
            c=dict(d)
        # 环境变量覆盖（Railway Variables 优先）
        env_map={"LLM_API_KEY":"llm_api_key","LLM_BASE_URL":"llm_base_url","TEXT_MODEL":"text_model",
                 "IMAGE_API_KEY":"image_api_key","IMAGE_BASE_URL":"image_base_url","IMAGE_MODEL":"image_model"}
        for envk,ck in env_map.items():
            v=os.environ.get(envk)
            if v: c[ck]=v
        return c
    def _load_styles(self):
        st={}
        dp=STYLE_DIR
        if os.path.isdir(dp):
            for fn in sorted(glob.glob(os.path.join(dp,"*.json"))):
                try:
                    with open(fn,"r",encoding="utf-8") as f: d=json.load(f)
                    n=d.get("style_name",""); 
                    if n: d.setdefault("art_style","");d.setdefault("base_positive","");d.setdefault("dynamic_subject_generate_prompt","");st[n]=d
                except: pass
        return st
    def save_config(self,c):
        self.config.update(c);
        with open(os.path.join(BASE_DIR,"config.json"),"w",encoding="utf-8") as f: json.dump(self.config,f,ensure_ascii=False,indent=2)
        return {"ok":True}
    def create_style(self,d):
        name=d.get("style_name","").strip()
        if not name: return {"ok":False,"error":"名称不能为空"}
        fp=os.path.join(BASE_DIR,"styles",f"{name}.json")
        if os.path.exists(fp): return {"ok":False,"error":"同名风格已存在"}
        style={
            "style_name":name,
            "art_style":d.get("art","cinematic environment concept art, realistic render"),
            "style_type":"场景概念美术",
            "render_type":"写实渲染",
            "base_positive":d.get("positive","超广角大全景，低角度仰拍，纵深透视，大气透视，电影级布光"),
            "base_negative":d.get("negative","卡通，二次元，鲜艳高饱和，干净崭新建筑"),
            "style_keywords_short":d.get("category","自定义"),
            "core_mood":"自定义氛围",
            "scene_category":[d.get("category","自定义")],
            "dynamic_subject_generate_prompt":d.get("gen_prompt","生成巨构场景主体"),
            "camera_settings":{"lens_type":"超广角","perspective":"低角度","shot_type":"全景","depth_of_field":"远景清晰","composition_rule":"主体占大部分画面"},
            "light_atmosphere":{"light_type":"侧逆光","time_preference":"黄昏","atmosphere_effect":"薄雾","forbidden_light":"平光"},
            "material_texture":{"main_material":"风化石材","surface_feature":"风化痕迹","avoid_material":"抛光材质"},
            "color_system":{"base_tone":"低灰度","main_color":"中性色","accent_color":"微弱暖光","color_rule":"低饱和"},
            "sampler_config":{"sampler":"dpmpp_2m","scheduler":"karras","steps":24,"cfg_scale":7,"width":1792,"height":1024},
            "caption_group":{"short_text":f"{name} #概念艺术","medium_text":f"{name}场景静静矗立","long_text":f"{name}宏大场景，感受史诗氛围","hashtags":["概念场景","AI绘画"]},
            "bgm_keywords":"epic ambient, lonely orchestral",
            "config_note":f"通过页面创建的{name}风格"
        }
        with open(fp,"w",encoding="utf-8") as f: json.dump(style,f,ensure_ascii=False,indent=2)
        self.STYLES=self._load_styles()
        self.STYLE_NAMES=list(self.STYLES.keys())
        return {"ok":True}
    def get_init(self):
        return {"names":self.STYLE_NAMES,"selected":self.style_name,"style":self.STYLE,
                "config":{k:self.config[k] for k in ["llm_api_key","llm_base_url","text_model","image_api_key","image_base_url","image_model","custom_suffix","selected_style","keep_human"]}}
    def gen_subject_ideas(self,style_name=""):
        try:
            sty=self.STYLES.get(style_name,{}) if style_name else {}
            kw=sty.get("style_keywords_short","") or ""
            mood=sty.get("core_mood","") or ""
            mat=sty.get("material_texture",{}).get("main_material","") or ""
            ctx=f"【风格关键词】{kw}\n【风格氛围】{mood}\n【核心材质】{mat}"
            prompt=f"""你是史诗场景创意大师，专精于营造孤寂、震撼、空旷的视觉氛围。当前风格「{style_name}」，风格特征如下：
{ctx}
请输出5个JSON对象，每行一个，严格遵循以下格式，不要任何多余文字：
{{"subject":"环境地貌+巨型主体建筑+空间位置形态","target_style":"{style_name}"}}

写作规范：
- 长度充足，禁止短句
- 句式：环境地貌 + 巨型主体建筑 + 空间位置形态
- ⚠️ 核心情绪：孤寂、空旷、压迫感——通过巨大 vs 渺小的对比来制造震撼
- 关键词取向：苍凉、荒芜、沉默、无垠、沉寂、肃穆、萧瑟、死寂
- 禁止人物、特写、小型物件
- target_style必须严格等于"{style_name}"，一字不差

合格示例：
{{"subject":"茫茫冰原深处，冰封已久的巨型环形石质堡垒静静矗立峡谷，万籁俱寂中唯有寒风呼啸","target_style":"{style_name}"}}"""
            h=self._headers("llm")
            for attempt in range(3):
                p={"model":self.config.get("text_model","deepseek-v4-flash"),
                   "messages":[{"role":"user","content":prompt}],
                   "max_tokens":600,"temperature":0.8}
                r=requests.post(f"{self.config.get('llm_base_url','https://api.apimart.ai/v1')}/chat/completions",headers=h,json=p,timeout=30)
                r.raise_for_status()
                txt=r.json()["choices"][0]["message"]["content"]
                import re
                subs=re.findall(r'"subject"\s*:\s*"([^"]+)"',txt)
                styles=re.findall(r'"target_style"\s*:\s*"([^"]+)"',txt)
                # 校验 target_style 必须匹配选中风格
                valid=[]
                for i,s in enumerate(subs):
                    ts=styles[i] if i<len(styles) else ""
                    if not style_name or ts==style_name:
                        valid.append(s)
                if valid: return {"ok":True,"ideas":valid[:5],"style_ok":len(valid)==len(subs)}
                prompt='上次输出风格不匹配，请严格确保target_style="'+style_name+'"。只输出JSON：\n{"subject":"...","target_style":"'+style_name+'"}\n每行一个，共5个。'
            return {"ok":False,"error":"LLM三次风格均不匹配"}
        except Exception as e: return {"ok":False,"error":f"灵感生成异常: {str(e)[:80]}"}
    def gen_desc(self,subject,count,rotate=False,style_name=""):
        if rotate and self.STYLE_NAMES:
            self._ri=getattr(self,'_ri',0)+1
            hint=self.STYLE_NAMES[(self._ri-1)%len(self.STYLE_NAMES)]
        else: hint=""
        sty=self.STYLES.get(style_name,{}) if style_name else {}
        mood=sty.get("core_mood","") or ""
        if subject:
            ins=f"""围绕主题「{subject}」生成{count}条场景描述JSON，每行一个：
{{"subject":"场景描述文本","target_style":"{style_name}"}}

面向gpt-image-2绘图模型优化，规范：
- 每条同一建筑，**光线、色调、氛围全部锁定一致**，只变化视角构图
- 视角变化：远景全景（突出孤寂空旷）、中景压缩感、仰视压迫感（突出建筑巨大）、侧翼视角、俯瞰视角
- ⚠️ 核心情绪：孤寂、震撼、空旷，通过巨大建筑对比渺小环境来制造压迫感
- 关键词取向：苍凉、荒芜、沉寂、肃穆、萧瑟、死寂、无声、无垠
- subject要求**100-150字**，强化：空间层次（前后远近）、材质质感（石材纹理/风化/锈蚀）、光线方向与色温
- 结构必须包含：地貌环境 + 建筑主体形态 + 结构细节（支柱/拱券/塔楼/台阶/穹顶等）+ 材质质感 + 空间位置
- 句式：环境地貌 + 巨型主体建筑 + 结构细节描述 + 空间位置形态
- ⚠️ 色彩基调、光线时段必须全统一，不能轮换变化
- 禁止人物、特写、小型物件（人物由后续优化步骤统一添加）
- 禁止短句、禁止笼统概括"""
        else:
            ins=f"""当前风格「{style_name}」氛围：{mood}。生成{count}条场景描述JSON，每行一个：
{{"subject":"场景描述文本","target_style":"{style_name}"}}

面向gpt-image-2绘图模型优化，规范：
- 每条同一建筑，**光线、色调、氛围全部锁定一致**，只变化视角构图
- 视角变化：远景全景（突出孤寂空旷）、中景压缩感、仰视压迫感（突出巨大）、侧翼视角
- ⚠️ 核心情绪：孤寂、震撼、空旷，通过巨大建筑对比渺小环境制造压迫感
- 关键词取向：苍凉、荒芜、沉寂、肃穆、萧瑟、死寂、无声
- subject要求**100-150字**，强化：空间层次、材质质感、光线方向与色温
- 结构必须包含：地貌环境 + 建筑主体形态 + 结构细节（支柱/拱券/塔楼/台阶/穹顶等）+ 材质质感 + 空间位置
- 句式：环境地貌 + 巨型主体建筑 + 结构细节描述 + 空间位置形态
- ⚠️ 色彩基调、光线时段必须全统一
- target_style必须="{style_name}"
- 禁止人物、特写、小型物件（人物由后续优化步骤统一添加）
- 禁止短句、禁止笼统概括"""
        try:
            h=self._headers("llm")
            p={"model":self.config.get("text_model","deepseek-v4-flash"),
               "messages":[{"role":"user","content":ins}],"max_tokens":8192,"temperature":0.5}
            r=requests.post(f"{self.config.get('llm_base_url','https://api.apimart.ai/v1')}/chat/completions",headers=h,json=p,timeout=60)
            r.raise_for_status()
            txt=r.json()["choices"][0]["message"]["content"]
            import re
            subjects=re.findall(r'"subject"\s*:\s*"([^"]+)"',txt)
            if not subjects:
                lines=[l.strip().lstrip("0123456789.、）) ") for l in txt.split("\n") if l.strip() and len(l.strip())>25]
            else:
                lines=subjects
            lines=[l for l in lines if len(l)>20]
            # 对每条描述词构建完整Prompt
            prompts=[self.build_prompt(d,False,False,self.config.get("keep_human",True),"1024x1792") for d in lines[:count]]
            return {"ok":True,"descriptions":lines[:count],"prompts":prompts,"hint":hint}
        except Exception as e: return {"ok":False,"error":f"LLM错误: {str(e)[:120]}"}
    def gen_one_desc(self):
        try:
            h=self._headers("llm")
            p={"model":self.config.get("text_model","deepseek-v4-flash"),
               "messages":[{"role":"user","content":"""输出一个JSON格式的巨构场景描述，不要任何多余文字：
{"subject":"场景描述文本","target_style":"风格名称"}

写作规范：
- 句式：环境地貌 + 巨型主体建筑 + 空间位置形态
- 长度60-100字，包含：建筑形态、材质纹理、光线氛围、空间尺度
- 只描述宏观全景，禁止人物、特写、小型物件
- 影视概念原画叙事感
- 禁止短句"""}],
               "max_tokens":400,"temperature":0.9}
            r=requests.post(f"{self.config.get('llm_base_url','https://api.apimart.ai/v1')}/chat/completions",headers=h,json=p,timeout=30)
            r.raise_for_status()
            txt=r.json()["choices"][0]["message"]["content"]
            import re
            m=re.search(r'"subject"\s*:\s*"([^"]+)"',txt)
            raw=m.group(1) if m else txt.strip().strip("\"'")
            if len(raw)<20: raw="云海断崖之上，矗立一座布满远古浮雕的巨型通天祭坛"
            prompt=self.build_prompt(raw,False,False,self.config.get("keep_human",True),"1024x1792")
            return {"ok":True,"desc":raw,"prompt":prompt}
        except Exception as e: return {"ok":False,"error":str(e)[:100]}
    def optimize_descs(self,descs,style=""):
        if not descs: return {"ok":False,"error":"无描述词"}
        try:
            h=self._headers("llm")
            txt="\n".join([f"{i+1}. {d}" for i,d in enumerate(descs)])
            p={"model":self.config.get("text_model","deepseek-v4-flash"),
               "messages":[{"role":"user","content":f"""你是一名gpt-image-2绘图模型的提示词优化师。对以下{len(descs)}条巨构场景描述词进行**自由重构优化**，目标是让gpt-image-2理解得更准、画得更好。

**你可以做的（不限以下）：**
- 打乱重组语序结构，让描述更符合绘图模型的理解习惯
- 改写润色，用更具画面感的语言替换平淡表达
- 增删调整，补充缺失的视觉细节，删减冗余
- 在每条场景中自然地融入一个极小的人物（位置姿态适配建筑环境，不是纯剪影，保留轮廓细节但体积极小不占视觉中心）
- 强化空间层次、材质质感、光线方向与色温、景深

**约束：**
- 保持原主题和风格「{style}」不变
- 保持原有视角构图方向（远景/中景/仰视等）
- 每条约100-150字，色调整体统一

只返回优化后的文本，每行一条，不要编号，不要JSON，不要解释：

{txt}"""}],
               "max_tokens":4096,"temperature":0.5}
            r=requests.post(f"{self.config.get('llm_base_url','https://api.apimart.ai/v1')}/chat/completions",headers=h,json=p,timeout=60)
            r.raise_for_status()
            raw=r.json()["choices"][0]["message"]["content"]
            lines=[l.strip().lstrip("0123456789.、）) ") for l in raw.split("\n") if l.strip() and len(l.strip())>20]
            if not lines: return {"ok":False,"error":"优化返回为空"}
            prompts=[self.build_prompt(d,False,False,self.config.get("keep_human",True),"1024x1792") for d in lines[:len(descs)]]
            return {"ok":True,"optimized":lines[:len(descs)],"prompts":prompts}
        except Exception as e: return {"ok":False,"error":f"优化异常: {str(e)[:80]}"}
    def build_prompt(self,desc,comp=False,light=False,human=True,size="1024x1792"):
        bp=self.STYLE.get("base_positive",""); art=self.STYLE.get("art_style","")
        if comp:
            comps=["轻微偏移中心构图，建筑偏左放置","俯仰角度微调，镜头略向下倾斜","水平线偏移，建筑偏右占据2/3画面","画面轻微旋转，增加不稳定感"]
            bp+=f"，{__import__('random').choice(comps)}"
        if light:
            lights=["晨雾浓度增加，光线更柔和","暮色更深，冷蓝色调为主","霞光增强，金色轮廓光更明显","阴沉天光，无直射光，漫反射为主","薄暮时分，天边残留微弱暖光"]
            bp+=f"，{__import__('random').choice(lights)}"
        p=f"{desc}, {art}, {bp}" if art else desc
        # 如果描述词已包含人物（优化后），不再追加随机人物
        if human and not any(w in desc for w in ["人影","剪影","人物","行人","身影","背影","骑手"]):
            import random as _r
            pos=_r.choice(["画面底部远景","画面中景一侧","画面近景边缘","画面偏下位置","巨大门洞下方","石阶尽头","平台边缘"])
            pose=_r.choice(["静立","缓步前行","坐","躺卧","倚靠石柱","蹲跪","骑马","撑伞站","拄杖而立","牵驼而行","负手而立","盘腿坐","侧卧","躬身前行","骑行","撑篙而立"])
            act=_r.choice(["仰望巨构","面朝建筑方向","背对镜头眺望远方","低头前行","抬头凝望","驻足观望","缓缓走向深处"])
            p+=f"，{pos}一个渺小的黑色剪影{pose}，{act}，体量极其微小仅作尺度参照"
        # 标注画幅尺寸
        size_map={"1024x1024":"方形构图1:1","1792x1024":"横屏宽幅16:9","1024x1792":"竖屏9:16","1344x768":"宽屏"}
        sn=size_map.get(size,"")
        if sn: p+=f"，{sn}"
        sfx=self.config.get("custom_suffix","")
        if sfx: p+=f", {sfx}"
        return p
    def generate(self,desc="",comp=False,light=False,size="1024x1792",prompt="",human=True):
        if not prompt: prompt=self.build_prompt(desc,comp,light,human,size)
        try:
            h=self._headers("img")
            p={"model":self.config.get("image_model","gpt-image-2-official"),"prompt":prompt,"n":1,"size":size,"response_format":"b64_json"}
            r=requests.post(f"{self.config.get('image_base_url','https://api.apimart.ai/v1')}/images/generations",headers=h,json=p,timeout=30)
            rd=r.json()
            tid=rd.get("data",[{}])[0].get("task_id")
            if not tid: return {"ok":False,"error":f"提交失败: {str(rd)[:120]}"}
            base=self.config.get("image_base_url","https://api.apimart.ai/v1")
            mx=self.config.get("max_polls",120)
            for i in range(mx):
                try:
                    time.sleep(2)
                    r2=requests.get(f"{base}/tasks/{tid}?language=zh",headers=h,timeout=30);d2=r2.json()
                    st=d2.get("data",{}).get("status","")
                    if st=="completed":
                        imgs=d2.get("data",{}).get("result",{}).get("images",[])
                        if imgs:
                            u=imgs[0].get("url")
                            if isinstance(u,list): u=u[0]
                            if not u: return {"ok":False,"error":"无图片URL"}
                            rd=requests.get(u,timeout=30,stream=True)
                            rd.raw.decode_content=True
                            if rd.status_code!=200: return {"ok":False,"error":f"图片下载失败: HTTP {rd.status_code}"}
                            b64=base64.b64encode(rd.content).decode()
                            # 保存到历史库
                            try:
                                ts=datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
                                hdir=os.path.join(BASE_DIR,"history")
                                os.makedirs(hdir,exist_ok=True)
                                # 保存图片
                                img_data=base64.b64decode(b64)
                                img_path=os.path.join(hdir,f"{ts}.png")
                                with open(img_path,"wb") as f: f.write(img_data)
                                # 保存提示词
                                with open(os.path.join(hdir,f"{ts}.txt"),"w",encoding="utf-8") as f:
                                    f.write(prompt)
                            except: pass
                            return {"ok":True,"b64":b64,"prompt":prompt}
                        return {"ok":False,"error":"无结果"}
                    elif st in ("failed","cancelled"):
                        err=d2.get("data",{}).get("error","") or "失败"
                        return {"ok":False,"error":f"任务{st}: {err}"}
                except Exception as pe:
                    if i<mx-1: time.sleep(2); continue
                    return {"ok":False,"error":f"轮询异常: {str(pe)[:60]}"}
            return {"ok":False,"error":"超时"}
        except Exception as e: return {"ok":False,"error":str(e)[:100]}
    def _headers(self,typ):
        key_map={"img":"image"}
        k=self.config.get(f"{key_map.get(typ,typ)}_api_key",""); 
        if not k: raise ValueError(f"缺少 {typ} API Key，请在设置中配置")
        return {"Authorization":f"Bearer {k}","Content-Type":"application/json","Accept-Encoding":"identity"}
backend=Backend()

AUTH_TOKEN = os.environ.get("AUTH_TOKEN","")

class Handler(http.server.BaseHTTPRequestHandler):
    def _check_auth(self):
        if not AUTH_TOKEN: return True
        ck=self.headers.get("Cookie","")
        return f"token={AUTH_TOKEN}" in ck
    def _login_page(self):
        self.send_response(200);self.send_header("Content-Type","text/html;charset=utf-8");self.end_headers()
        self.wfile.write(f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>街灯AI--场景生成器</title>
<style>
body{{font-family:system-ui;background:#0f0f13;color:#e8e8ed;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}}
.box{{background:#18181c;border:1px solid #333;border-radius:12px;padding:40px;width:340px;text-align:center}}
.box h2{{margin-bottom:20px;font-size:18px;color:var(--accent2);}}
.box input{{width:100%;padding:10px;border:1px solid #333;border-radius:6px;background:#222;color:#e8e8ed;font-size:14px;outline:none;margin-bottom:16px;box-sizing:border-box}}
.box button{{width:100%;padding:10px;border:none;border-radius:6px;background:#6c5ce7;color:#fff;font-size:14px;cursor:pointer}}
.box button:hover{{background:#5a4bd1}}
.box .err{{color:#e17055;font-size:13px;margin-bottom:10px}}
</style></head><body>
<div class="box"><h2>🔐 JaydenAI</h2>
<form method="post" action="/">
<input type="password" name="token" placeholder="输入访问密码" autofocus/>
<button type="submit">进入</button>
</form></div></body></html>""".encode())
    def do_GET(self):
        if not self._check_auth():
            self._login_page(); return
        if self.path=="/":
            self.send_response(200);self.send_header("Content-Type","text/html;charset=utf-8");self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))
        elif self.path=="/api/init": self._json(backend.get_init())
        elif self.path=="/api/list_images": self._json(self._list_images())
        elif self.path.startswith("/api/image/"):
            rel=self.path.replace("/api/image/","").replace("/",os.sep)
            fp=os.path.join(BASE_DIR,rel)
            if os.path.exists(fp):
                self.send_response(200);self.send_header("Content-Type","image/png");self.end_headers()
                with open(fp,"rb") as f:self.wfile.write(f.read())
            else:self.send_error(404)
        elif self.path.startswith("/api/open_dir"):
            os.startfile(os.path.join(BASE_DIR,"output"));self._json({"ok":True})
        else: self.send_error(404)
    def do_POST(self):
        if AUTH_TOKEN and not self._check_auth():
            self._json({"ok":False,"error":"未授权"}); return
        if self.path=="/":
            length=int(self.headers.get("Content-Length",0))
            body=self.rfile.read(length).decode() if length else ""
            import urllib.parse
            params=urllib.parse.parse_qs(body)
            tk=params.get("token",[None])[0]
            if tk==AUTH_TOKEN:
                self.send_response(302);self.send_header("Set-Cookie",f"token={AUTH_TOKEN}; Path=/; Max-Age=86400");self.send_header("Location","/");self.end_headers()
            else:
                self.send_response(200);self.send_header("Content-Type","text/html;charset=utf-8");self.end_headers()
                self.wfile.write(f"""<!DOCTYPE html><html><body style="background:#0f0f13;color:#e8e8ed;display:flex;align-items:center;justify-content:center;height:100vh;font-family:system-ui"><div style="text-align:center"><p style="color:#e17055;margin-bottom:16px">❌ 密码错误</p><a href="/" style="color:#6c5ce7">重新输入</a></div></body></html>""".encode())
            return
        length=int(self.headers.get("Content-Length",0))
        body=self.rfile.read(length).decode() if length else ""
        data=json.loads(body) if body else {}
        p=urlparse(self.path).path;resp={"ok":False}
        try:
            if p=="/api/gen_desc": resp=backend.gen_desc(data.get("subject",""),int(data.get("count",3)),data.get("rotate",False),backend.style_name)
            elif p=="/api/gen_ideas": resp=backend.gen_subject_ideas(data.get("style",""))
            elif p=="/api/gen_one": resp=backend.gen_one_desc()
            elif p=="/api/optimize": resp=backend.optimize_descs(data.get("descriptions",[]),data.get("style",""))
            elif p=="/api/generate": resp=backend.generate(data.get("desc",""),data.get("comp",False),data.get("light",False),data.get("size","1024x1792"),data.get("prompt",""),data.get("human",True))
            elif p=="/api/save_config": resp=backend.save_config(data)
            elif p=="/api/set_style":
                backend.style_name=data.get("name","");backend.STYLE=backend.STYLES.get(backend.style_name,{});
                backend.config["selected_style"]=backend.style_name;backend.save_config(backend.config);resp={"ok":True}
            elif p=="/api/create_style": resp=backend.create_style(data)
            else: resp={"ok":False,"error":"unknown"}
        except Exception as e: resp={"ok":False,"error":str(e)[:200]}
        self._json(resp)
    def _json(self,data):
        self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Access-Control-Allow-Origin","*");self.end_headers()
        self.wfile.write(json.dumps(data,ensure_ascii=False).encode("utf-8"))
    def log_message(self,*a): pass
    def _list_images(self):
        imgs=[]
        hdir=os.path.join(BASE_DIR,"history")
        # 优先从历史库读取
        if os.path.exists(hdir):
            files=[f for f in os.listdir(hdir) if f.lower().endswith((".png",".jpg",".jpeg"))]
            files.sort(key=lambda f: os.path.getmtime(os.path.join(hdir,f)), reverse=True)
            seen={}
            for f in files:
                base=os.path.splitext(f)[0]
                if base in seen: continue
                if f.lower().endswith((".png",".jpg",".jpeg")):
                    fp=os.path.join(hdir,f)
                    txt_path=os.path.join(hdir,base+".txt")
                    prompt=""
                    if os.path.exists(txt_path):
                        with open(txt_path,"r",encoding="utf-8") as tf: prompt=tf.read()[:200]
                    seen[base]=True
                    imgs.append({"name":f,"prompt":prompt,"url":f"/api/image/{os.path.relpath(fp,BASE_DIR).replace(os.sep,'/')}"})
        # 如果历史库为空，扫描旧output目录
        if not imgs:
            for root,dirs,files in os.walk(os.path.join(BASE_DIR,"output")):
                imgs_png=[f for f in files if f.lower().endswith((".png",".jpg",".jpeg"))]
                imgs_png.sort(key=lambda f: os.path.getmtime(os.path.join(root,f)), reverse=True)
                for f in imgs_png[:50]:
                    fp=os.path.join(root,f)
                    imgs.append({"name":f,"prompt":"","url":f"/api/image/{os.path.relpath(fp,BASE_DIR).replace(os.sep,'/')}"})
            for root,dirs,files in os.walk(os.path.join(BASE_DIR,"output_jugou_differ")):
                imgs_png=[f for f in files if f.lower().endswith((".png",".jpg",".jpeg"))]
                imgs_png.sort(key=lambda f: os.path.getmtime(os.path.join(root,f)), reverse=True)
                for f in imgs_png[:50]:
                        imgs.append({"name":f,"prompt":"","url":f"/api/image/{os.path.relpath(fp,BASE_DIR).replace(os.sep,'/')}"})
        return {"ok":True,"images":imgs[:100]}

HTML=r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>街灯AI--场景生成器</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter','Segoe UI',system-ui,sans-serif;background:#0f0f13;color:#e8e8ed;height:100vh;display:flex;flex-direction:column;font-size:14px;position:relative;overflow:hidden}
/* 背景动态渐变光晕 */
body::before{content:'';position:fixed;top:-20%;left:-10%;width:60%;height:60%;background:radial-gradient(ellipse at center,rgba(108,92,231,.08) 0%,transparent 70%);animation:dGlow 12s ease-in-out infinite alternate;pointer-events:none;z-index:0}
body::after{content:'';position:fixed;bottom:-20%;right:-10%;width:50%;height:50%;background:radial-gradient(ellipse at center,rgba(0,206,201,.06) 0%,transparent 70%);animation:dGlow2 15s ease-in-out infinite alternate;pointer-events:none;z-index:0}
@keyframes dGlow{0%{transform:translate(0,0) scale(1)}100%{transform:translate(10%,8%) scale(1.2)}}
@keyframes dGlow2{0%{transform:translate(0,0) scale(1)}100%{transform:translate(-8%,-5%) scale(1.15)}}
:root{--bg:#0f0f13;--card:#18181c;--surf:#22222a;--input:#2a2a32;--border:#33333d;--accent:#6c5ce7;--accent2:#00cec9;--warn:#e17055;--text:#e8e8ed;--body:#b0b0b8;--hint:#6a6a74}
.header{display:flex;align-items:center;padding:10px 20px;gap:12px;background:linear-gradient(135deg,#141420 0%,#1c1c30 50%,#141420 100%);border-bottom:1px solid var(--border);flex-shrink:0;position:relative;z-index:1}
.header::after{content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent 0%,rgba(108,92,231,.04) 50%,transparent 100%);pointer-events:none}
.header h1{font-size:16px;font-weight:700}
.header select{background:var(--surf);color:var(--text);border:1px solid var(--border);border-radius:5px;padding:5px 10px;font-size:13px;outline:none;cursor:pointer}
.header .tab{background:none;border:none;color:var(--hint);font-size:13px;cursor:pointer;padding:5px 12px;border-radius:4px;font-weight:600}
.header .tab:hover{color:var(--text);background:var(--surf)}
.header .tab.act{color:var(--accent2);background:var(--surf)}
.tbar{display:flex;align-items:center;gap:8px;padding:4px 16px;background:rgba(34,34,42,.55);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);font-size:12px;color:var(--hint);flex-shrink:0;min-height:30px;position:relative;z-index:1;border-bottom:1px solid rgba(51,51,61,.3)}
.gallery{display:none;padding:12px 16px;flex:1;overflow-y:auto}
.gallery.show{display:block}
.gallery .g-item{display:flex;margin:0 0 10px 0;background:var(--card);border-radius:8px;border:1px solid var(--border);overflow:hidden;cursor:pointer;gap:0}
.gallery .g-item:hover{border-color:var(--accent)}
.gallery .g-item img{width:160px;height:100px;object-fit:cover;flex-shrink:0;cursor:zoom-in}
.gallery .g-item .g-info{flex:1;padding:8px 10px;overflow:hidden;display:flex;flex-direction:column;gap:4px}
.gallery .g-item .gl{font-size:10px;color:var(--hint);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gallery .g-item .gp{font-size:11px;color:var(--body);line-height:1.5;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.gwrap{flex:1;overflow-y:auto;padding:12px 16px 100px;position:relative;z-index:1}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:12px}
.card{background:var(--card);border-radius:8px;border:1px solid var(--border);padding:12px;display:flex;flex-direction:column;gap:6px;position:relative;transition:border-color .2s}
.card:hover{border-color:rgba(108,92,231,.3)}
.card::before{content:'';position:absolute;inset:-1px;border-radius:9px;background:linear-gradient(135deg,transparent 40%,rgba(108,92,231,0) 100%);opacity:0;transition:opacity .3s;pointer-events:none;z-index:-1}
.card:hover::before{opacity:1;background:linear-gradient(135deg,rgba(108,92,231,.08) 0%,rgba(0,206,201,.04) 50%,transparent 100%)}
.card .idx{font-size:11px;color:var(--hint);font-weight:600}
.card .desc{font-size:13px;color:var(--body);line-height:1.6;min-height:38px;cursor:pointer;padding:4px 6px;border-radius:4px}
.card .desc:hover{background:var(--input)}
.card .desc[contenteditable=true]{background:var(--input);outline:1px solid var(--accent)}
.card .acts{display:flex;gap:4px;flex-wrap:wrap}
.card .prev{background:var(--input);border-radius:5px;min-height:110px;display:flex;align-items:center;justify-content:center;overflow:hidden;border:1px solid var(--border)}
.card .prev img{max-width:100%;max-height:150px;object-fit:contain;animation:fadeIn .3s;cursor:zoom-in}
.card.has-img{border-color:rgba(108,92,231,.25)}
.card.has-img::before{opacity:1;background:linear-gradient(135deg,rgba(108,92,231,.06) 0%,rgba(0,206,201,.03) 50%,transparent 100%)}
/* 图片放大预览 */
.zoom-layer{display:none;position:fixed;inset:0;background:rgba(0,0,0,.82);z-index:200;cursor:zoom-out;align-items:center;justify-content:center}
.zoom-layer.show{display:flex}
.zoom-layer img{max-width:90vw;max-height:90vh;object-fit:contain;border-radius:8px;box-shadow:0 8px 40px rgba(0,0,0,.5);animation:fadeIn .2s}
@media(max-width:768px){.zoom-layer img{max-width:96vw;max-height:80vh}.bbar{z-index:52!important}}
@keyframes fadeIn{from{opacity:0;transform:scale(.95)}to{opacity:1;transform:scale(1)}}
.card .prev .ph{color:var(--hint);font-size:10px}
.card-tags{display:flex;gap:6px;font-size:9px;color:var(--hint);padding:2px 0 0}
@keyframes fadeIn{from{opacity:0;transform:scale(.95)}to{opacity:1;transform:scale(1)}}
.bbar{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);display:inline-flex;flex-direction:column-reverse;align-items:center;z-index:51}
.bbar-main{display:flex;align-items:center;gap:8px;padding:10px 18px;background:rgba(24,24,28,.88);border:1px solid var(--border);border-radius:12px;backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);box-shadow:0 4px 24px rgba(0,0,0,.3)}
.bbar-adjacent{display:none;flex-direction:column;gap:10px;padding:14px 18px;background:rgba(24,24,28,.88);border:1px solid var(--border);border-bottom:none;border-radius:12px 12px 0 0;backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);margin-bottom:-1px}
.bbar-adjacent.show{display:flex}
.bbar-adjacent .row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.bbar-adjacent .row label{font-size:11px;color:var(--hint);white-space:nowrap}
.bbar-adjacent .row input{width:160px;background:var(--input);border:1px solid var(--border);border-radius:4px;padding:3px 8px;font-size:11px;color:var(--text);outline:none}
.bbar-adjacent .chip{display:inline-flex;padding:2px 8px;border-radius:4px;font-size:10px;cursor:pointer;background:var(--surf);color:var(--hint);border:1px solid var(--border);transition:all .1s;user-select:none}
.bbar-adjacent .chip:hover{color:var(--text);border-color:var(--accent)}
.bbar-adjacent .chip.sel{background:rgba(108,92,231,.2);color:var(--accent);border-color:var(--accent)}
.bbar input{width:200px;background:var(--input);border:1px solid var(--border);border-radius:5px;padding:6px 10px;font-size:12px;color:var(--text);outline:none}
.bbar input:focus{border-color:var(--accent)}
.bbar .cnt{width:50px;text-align:center;min-width:50px}
.btng{display:inline-flex;align-items:center;gap:4px;padding:5px 12px;border-radius:5px;font-size:11px;font-weight:600;border:none;cursor:pointer;transition:all .12s;line-height:1}
.btng-p{background:linear-gradient(135deg,#6c5ce7,#a29bfe);color:#fff}
.btng-p:hover{transform:translateY(-1px);box-shadow:0 2px 8px rgba(108,92,231,.2)}
.btng-s{background:var(--surf);color:var(--body);border:1px solid var(--border)}
.btng-s:hover{background:var(--input);color:var(--text);border-color:var(--accent)}
.btng-d{background:transparent;color:var(--hint);border:1px solid var(--border)}
.btng-d:hover{color:var(--text);border-color:var(--accent)}
.btng:disabled{opacity:.4;cursor:not-allowed;transform:none!important}
.bar{display:flex;gap:8px;padding:0;margin:0 0 8px 0;flex-wrap:wrap}
.modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:100;align-items:center;justify-content:center}
.modal.show{display:flex}
.modal-c{background:var(--card);border-radius:12px;padding:20px;width:440px;border:1px solid var(--border);max-height:85vh;overflow-y:auto}
.modal-acts{display:flex;gap:8px;justify-content:flex-end;margin-top:12px}
.mg{margin-bottom:6px}
.mg label{display:block;font-size:11px;color:var(--hint);margin-bottom:2px}
.mg input,.mg select{width:100%;background:var(--input);border:1px solid var(--border);border-radius:5px;padding:5px 8px;font-size:11px;color:var(--text);outline:none}
@media(max-width:768px){.mg input,.mg select{font-size:14px;padding:8px 10px}}
.loading{display:inline-block;width:10px;height:10px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .6s linear infinite;vertical-align:middle;margin-right:2px}
@keyframes spin{to{transform:rotate(360deg)}}
.hidden{display:none!important}
::-webkit-scrollbar{width:4px}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:4px}
/* 手机端适配 */
@media(max-width:768px){
body{font-size:13px;overflow:auto}
.header{padding:8px 10px;gap:6px;flex-wrap:wrap}.header h1{font-size:14px;width:100%;text-align:center;margin-bottom:2px}
.header select{font-size:11px;padding:4px 6px;flex:1;min-width:0}
.header .tab{font-size:11px;padding:4px 8px}
.header .btng{font-size:9px!important;padding:2px 5px!important}
.header label{font-size:10px!important}
.grid{grid-template-columns:1fr!important;gap:8px}
.card{padding:8px}.card .desc{font-size:12px}.card .acts{gap:3px}
.card .btng{font-size:10px!important;padding:3px 8px!important}
.gwrap{padding:8px 8px 120px}.gallery{padding:8px}.gallery .g-item{flex-direction:column}.gallery .g-item img{width:100%;height:160px}
.bar{flex-wrap:wrap;gap:4px;padding:6px 8px;justify-content:center}
.bar .btng{font-size:10px!important;padding:3px 8px!important}
.bbar{bottom:8px}.bbar .btng{font-size:10px!important;padding:4px 10px!important}
.bbar-main{flex-wrap:wrap;gap:5px;padding:8px 10px;width:96vw;justify-content:center}
.bbar-main input{width:100%!important;font-size:14px!important;padding:8px 10px!important}
.bbar-main .cnt{width:50px!important;min-width:50px!important}
.bbar select{font-size:12px!important;padding:6px 8px!important}
.bbar-adjacent{padding:10px 12px;width:96vw}.bbar-adjacent .row{gap:4px}
.bbar-adjacent .row input{width:100%!important;font-size:13px!important;padding:6px 8px!important}
.bbar-adjacent .chip{font-size:10px!important;padding:3px 7px!important}
#advBtn{display:none!important}
.modal-c{width:92vw!important;max-height:90vh;padding:14px}
}
</style>
</head>
<body>
<div class="header">
 <h1>街灯AI--场景生成器</h1>
 <select id="styleSelect" onchange="setStyle(this.value)"></select>
 <button class="btng btng-d" style="font-size:10px;padding:2px 8px" onclick="showNewStyle()">+新建</button>
 <label style="font-size:11px;color:var(--hint);display:flex;align-items:center;gap:3px;cursor:pointer"><input type="checkbox" id="autoRotate" checked />轮换</label>
 <label style="font-size:11px;color:var(--hint);display:flex;align-items:center;gap:3px;cursor:pointer"><input type="checkbox" id="autoSwitch" />自动</label>
 <div style="flex:1"></div>
 <button class="tab act" onclick="showTab('gen')" id="tabGen">✨ 生成</button>
 <button class="tab" onclick="showTab('lib')" id="tabLib">📂 图库 <span id="galleryCount" style="font-size:9px;color:var(--accent2)"></span></button>
 <button class="btng btng-d" onclick="showSettings()">设置</button>
</div>

<div class="tbar" id="tbar"><span>就绪</span></div>

<div class="gwrap" id="gwrap">
 <div id="batchBar" class="bar hidden"></div>
 <div class="grid" id="cardGrid"></div>
</div>

<div class="gallery" id="gallery"></div>

<div class="bbar">
 <div class="bbar-main">
  <input id="subjInp" placeholder="输入主体灵感，或留空让AI自由发挥" />
  <input class="cnt" id="cntInp" type="number" min="1" max="20" value="5" />
  <label>张</label>
  <select id="sizeSelect" style="background:var(--input);border:1px solid var(--border);border-radius:5px;padding:4px 6px;font-size:11px;color:var(--text);outline:none;cursor:pointer">
   <option value="1024x1024">1:1 方</option>
   <option value="1792x1024">16:9 横</option>
   <option value="1024x1792" selected>9:16 竖</option>
   <option value="1344x768">宽屏</option>
  </select>
  <button class="btng btng-d" onclick="genIdeas()" id="ideaBtn">💡灵感</button>
  <button class="btng btng-p" onclick="batchGen()" id="genBtn">批量生成</button>
  <button class="btng btng-d" onclick="toggleAdv()" id="advBtn">⚙高级</button>
 </div>
 <div class="bbar-adjacent" id="advPanel">
  <div class="row">
   <label>后缀:</label>
   <input id="sfxInp" placeholder="film grain, cinematic color grading..." value="" />
   <span class="chip" data-val="film grain, cinematic color grading" onclick="toggleSfx(this)">胶片质感</span>
   <span class="chip" data-val="volumetric lighting, dramatic shadows" onclick="toggleSfx(this)">体积光</span>
   <span class="chip" data-val="ultra detailed, sharp focus, 8K" onclick="toggleSfx(this)">超清细节</span>
   <span class="chip" style="color:var(--warn)" onclick="clearSfx()">清空</span>
  </div>
  <div class="row">
   <button class="btng btng-d" onclick="toggleComp()" id="compBtn">构图微调</button>
   <button class="btng btng-d" onclick="toggleLight()" id="lightBtn">光影微调</button>
   <button class="btng btng-d" onclick="toggleHuman()" id="humanBtn">👤剪影</button>
  </div>
 </div>
</div>

<div id="setMod" class="modal"><div class="modal-c" id="setContent"></div></div>
<div class="zoom-layer" id="zoomLayer" onclick="closeZoom()"><img id="zoomImg" src="" alt="放大预览"/></div>

<script>
let CARDS=[],STYLES=[],CONFIG={},COMP=false,LIGHT=false,HUMAN=true;
async function api(path,data){
 console.log("api call:",path,data);
 const r=await fetch(path,{method:data?"POST":"GET",headers:{"Content-Type":"application/json"},body:data?JSON.stringify(data):null});
 const j=await r.json();console.log("api resp:",path,j);return j}
async function init(){
 const r=await api("/api/init");STYLES=r.names||[];CONFIG=r.config||{};
 const sel=document.getElementById("styleSelect");
 sel.innerHTML=STYLES.map(n=>`<option value="${n}"${n==r.selected?" selected":""}>${n}</option>`).join("");
 // 回填后缀
 const si=document.getElementById("sfxInp");
 if(CONFIG.custom_suffix){si.value=CONFIG.custom_suffix}
 HUMAN=CONFIG.keep_human!==false;
 const hb=document.getElementById("humanBtn");
 if(hb){hb.style.borderColor=HUMAN?"var(--accent2)":"var(--border)";hb.style.color=HUMAN?"var(--accent2)":"var(--hint)"}
 // 加载图库数量
 try{const g=await api("/api/list_images");const gc=document.getElementById("galleryCount");if(gc&&g.images){gc.textContent=g.images.length>0?`(${g.images.length})`:""}}catch(e){}
}init();
function st(msg,c){document.getElementById("tbar").innerHTML=`<span style="color:${c||'var(--hint)'}">${msg}</span>`}

function toggleComp(){COMP=!COMP;document.getElementById("compBtn").style.borderColor=COMP?"var(--accent)":"var(--border)";document.getElementById("compBtn").style.color=COMP?"var(--accent)":"var(--hint)"}
function toggleLight(){LIGHT=!LIGHT;document.getElementById("lightBtn").style.borderColor=LIGHT?"var(--accent2)":"var(--border)";document.getElementById("lightBtn").style.color=LIGHT?"var(--accent2)":"var(--hint)"}
function toggleAdv(){const p=document.getElementById("advPanel");const b=document.getElementById("advBtn");p.classList.toggle("show");b.textContent=p.classList.contains("show")?"⚙收起":"⚙高级";}
function toggleHuman(){
 HUMAN=!HUMAN;const el=document.getElementById("humanBtn");
 el.style.borderColor=HUMAN?"var(--accent2)":"var(--border)";el.style.color=HUMAN?"var(--accent2)":"var(--hint)";
 CONFIG.keep_human=HUMAN;api("/api/save_config",CONFIG);
}
function toggleSfx(el){
 el.classList.toggle("sel");
 const vals=[].map.call(document.querySelectorAll(".chip.sel"),c=>c.dataset.val).filter(Boolean);
 document.getElementById("sfxInp").value=vals.join(", ");
}
function clearSfx(){
 document.querySelectorAll(".chip.sel").forEach(c=>c.classList.remove("sel"));
 document.getElementById("sfxInp").value="";
}
function togglePrompt(i){
 const el=document.getElementById("desc"+i);
 if(el.textContent==CARDS[i].prompt){
  el.textContent=CARDS[i].desc;
  document.getElementById("toggle"+i).textContent="📄完整";
 }else{
  el.textContent=CARDS[i].prompt;
  document.getElementById("toggle"+i).textContent="📄精简";
 }
}
async function genIdeas(){
 const btn=document.getElementById("ideaBtn");btn.disabled=true;btn.innerHTML='<span class="loading"></span>';
 try{
  const style=document.getElementById("styleSelect").value;
  const r=await api("/api/gen_ideas",{style:style});
  console.log("genIdeas response:",r);
  if(!r.ok){st("灵感失败: "+(r.error||"无返回"),"var(--warn)");btn.disabled=false;btn.innerHTML="💡灵感";return}
  if(!r.ideas||!r.ideas.length){st("灵感失败: AI返回为空","var(--warn)");btn.disabled=false;btn.innerHTML="💡灵感";return}
  // style_ok=false表示风格不匹配已自动重试，轻提示通知用户
  if(r.style_ok===false){st("题材匹配异常，已自动重新生成","var(--warn)")}
  document.getElementById("subjInp").value=r.ideas[Math.floor(Math.random()*r.ideas.length)];
  st("灵感已填入","var(--accent2)");
 }catch(e){
  console.error("genIdeas error:",e);
  st("请求出错: "+e.message,"var(--warn)")
 }
 btn.disabled=false;btn.innerHTML="💡灵感";
}

 async function batchGen(){
 try{
 const subj=document.getElementById("subjInp").value.trim();
 const cnt=parseInt(document.getElementById("cntInp").value)||5;
 const rot=document.getElementById("autoRotate").checked;
 const sw=document.getElementById("autoSwitch").checked;
 const sfx=document.getElementById("sfxInp").value.trim();
 if(sfx!=CONFIG.custom_suffix){CONFIG.custom_suffix=sfx;await api("/api/save_config",CONFIG)}
 const btn=document.getElementById("genBtn");btn.disabled=true;btn.innerHTML='<span class="loading"></span>';
 st("生成描述词...","var(--accent)");
 const r=await api("/api/gen_desc",{subject:subj,count:cnt,rotate:rot});
 btn.disabled=false;btn.innerHTML="批量生成";
 if(!r.ok){st("失败: "+r.error,"var(--warn)");return}
 if(!r.descriptions||r.descriptions.length==0){st("无结果","var(--warn)");return}
 const grid=document.getElementById("cardGrid");
 grid.innerHTML="";CARDS=[];
 r.descriptions.forEach((d,i)=>{
  const fp=r.prompts?.[i]||d;
  CARDS.push({desc:d,img:null,prompt:fp});
  const c=document.createElement("div");c.className="card";
  c.innerHTML=`<div class="idx">#${i+1}
   <span style="float:right;font-size:9px;color:var(--accent2);cursor:pointer" onclick="togglePrompt(${i})" id="toggle${i}">📄完整</span></div>
   <div class="desc" id="desc${i}" ondblclick="editDesc(${i})">${d}</div>
   <div class="acts">
    <button class="btng btng-p" style="font-size:11px;padding:4px 10px" onclick="genImg(${i})">生图</button>
    <button class="btng btng-s" style="font-size:11px;padding:4px 10px" onclick="redoDesc(${i})">重写</button>
    <button class="btng btng-d hidden" style="font-size:9px;padding:2px 6px" id="save${i}" onclick="saveImg(${i})">保存</button>
   </div>
   <div class="prev" id="prev${i}"><span class="ph">等待生图...</span></div>
   <div class="card-tags" id="tags${i}">
    <span style="color:${HUMAN?'var(--accent2)':'var(--hint)'}">👤${HUMAN?'开':'关'}</span>
    <span>📐${document.getElementById('sizeSelect')?.value||'9:16'}</span>
   </div>
  `;
  grid.appendChild(c);
 });
 const bar=document.getElementById("batchBar");bar.classList.remove("hidden");
 bar.innerHTML=`<button class="btng btng-s" style="font-size:11px;padding:4px 10px" onclick="genAll()">全部生图</button>
  <button class="btng btng-s" style="font-size:11px;padding:4px 10px" onclick="saveAll()">批量保存</button>
  <button class="btng btng-d" style="font-size:11px;padding:4px 10px" onclick="optimizeAll()">✨AI优化</button>
  <button class="btng btng-d" style="font-size:11px;padding:4px 10px" onclick="redoAll()">全部重写</button>
  <span style="font-size:9px;color:var(--hint);margin-left:auto">双击描述词可编辑</span>`;
 st(`已生成 ${r.descriptions.length} 条`,"var(--accent2)");
 if(r.hint&&r.hint!=document.getElementById("styleSelect").value){
  if(document.getElementById("autoSwitch").checked){
   document.getElementById("styleSelect").value=r.hint;setStyle(r.hint)
  }else{st(`偏向「${r.hint}」可切换风格`,"var(--accent2)")}
 }
 }catch(e){st("异常: "+e.message,"var(--warn)");document.getElementById("genBtn").disabled=false;document.getElementById("genBtn").innerHTML="批量生成"}
}
function editDesc(i){
 const el=document.getElementById("desc"+i);el.contentEditable=true;el.focus();
 el.addEventListener("blur",()=>{el.contentEditable=false;CARDS[i].desc=el.textContent.trim()},{once:true});
}
function copyDesc(i){
 const t=CARDS[i]?.desc;if(t){navigator.clipboard.writeText(t);st("已复制","var(--accent2)")}
}
async function redoDesc(i){
 const btns=document.querySelectorAll(".card")[i]?.querySelectorAll("button");
 if(btns&&btns[1]){btns[1].disabled=true;btns[1].innerHTML='<span class="loading"></span>'}
 const r=await api("/api/gen_one");
 if(btns&&btns[1]){btns[1].disabled=false;btns[1].innerHTML="重写"}
 if(!r.ok)return;
 CARDS[i].desc=r.desc;CARDS[i].prompt=r.prompt||r.desc;
 document.getElementById("desc"+i).textContent=document.getElementById("toggle"+i)?.textContent=="📄精简"?r.prompt||r.desc:r.desc;
 document.getElementById("prev"+i).innerHTML='<span class="ph">等待生图...</span>';
 document.getElementById("save"+i).classList.add("hidden");st("已更新","var(--accent2)");
}
async function redoAll(){
 const btn=document.querySelector("#batchBar .btng-d");if(btn){btn.disabled=true;btn.innerHTML='<span class="loading"></span>'}
 for(let i=0;i<CARDS.length;i++){
  const r=await api("/api/gen_one");
  if(r.ok){
   CARDS[i].desc=r.desc;CARDS[i].prompt=r.prompt||r.desc;
   document.getElementById("desc"+i).textContent=r.desc;
   document.getElementById("prev"+i).innerHTML='<span class="ph">等待生图...</span>';
   document.getElementById("save"+i).classList.add("hidden");
  }
 }
 if(btn){btn.disabled=false;btn.innerHTML="全部重写"}
 st("全部已更新","var(--accent2)");
}
async function optimizeAll(){
 const btn=document.querySelector("#batchBar .btng-d:nth-child(3)");
 if(btn){btn.disabled=true;btn.innerHTML='<span class="loading"></span>'}
 st("LLM优化中...","var(--accent)");
 const descs=CARDS.map(c=>c.desc);
 const r=await api("/api/optimize",{descriptions:descs,style:document.getElementById("styleSelect").value});
 if(btn){btn.disabled=false;btn.innerHTML="✨AI优化"}
 if(!r.ok||!r.optimized){st("优化失败: "+(r.error||"未知"),"var(--warn)");return}
 for(let i=0;i<r.optimized.length&&i<CARDS.length;i++){
  CARDS[i].desc=r.optimized[i];CARDS[i].prompt=r.prompts?.[i]||r.optimized[i];
  document.getElementById("desc"+i).textContent=CARDS[i].prompt;
 }
 st("优化完成 "+r.optimized.length+" 条","var(--accent2)");
}
async function genImg(i){
 const d=CARDS[i]?.desc;if(!d)return;
 const sz=document.getElementById("sizeSelect").value;
 const btn=document.querySelectorAll(".card")[i]?.querySelector(".btng-p");
 if(btn){btn.disabled=true;btn.innerHTML='<span class="loading"></span>'}
 // 预览区显示加载中
 const pv=document.getElementById("prev"+i);
 pv.innerHTML='<span class="ph" style="color:var(--accent)"><span class="loading" style="width:14px;height:14px;border-width:2px"></span> 生图中...</span>';
 st(`生图中 ${i+1}/${CARDS.length}...`,"var(--accent)");
 try{
  const raw=await fetch("/api/generate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({desc:CARDS[i].desc,prompt:CARDS[i].prompt||CARDS[i].desc,comp:COMP,light:LIGHT,size:sz,human:HUMAN})});
  const txt=await raw.text();console.log("genImg raw:",txt);
  let r;
  try{r=JSON.parse(txt)}catch(e){st("生图异常: 返回非JSON: "+txt.slice(0,80),"var(--warn)");if(btn){btn.disabled=false;btn.innerHTML="生图"}return}
  if(btn){btn.disabled=false;btn.innerHTML="生图"}
  if(!r.ok||!r.b64){st("生图失败: "+(r.error||"无法解析错误"),"var(--warn)");return}
  document.getElementById("prev"+i).innerHTML=`<img src="data:image/png;base64,${r.b64}" onclick="zoomImg(${i})" />`;
  CARDS[i].img=r.b64;document.getElementById("save"+i).classList.remove("hidden");
  document.querySelectorAll(".card")[i]?.classList.add("has-img");
  st("完成","var(--accent2)");
 }catch(e){console.error("genImg err:",e);if(btn){btn.disabled=false;btn.innerHTML="生图"}st("生图异常: "+e.message,"var(--warn)")}
}
async function genAll(){for(let i=0;i<CARDS.length;i++){if(!CARDS[i].img)await genImg(i)}st("全部完成","var(--accent2)")}
function saveImg(i){
 const b64=CARDS[i]?.img;if(!b64)return;
 const a=document.createElement("a");a.href=`data:image/png;base64,${b64}`;
 a.download=`mg_${Date.now()}_${i+1}.png`;a.click();st("已保存","var(--accent2)");
}
function zoomImg(i){
 const b64=CARDS[i]?.img;if(!b64)return;
 document.getElementById("zoomImg").src=`data:image/png;base64,${b64}`;
 document.getElementById("zoomLayer").classList.add("show");
}
function closeZoom(){document.getElementById("zoomLayer").classList.remove("show")}
function reuseGallery(name){
 document.getElementById("subjInp").value=name.replace(/\.\w+$/,"");
 showTab("gen");
 st("已复用: "+name,"var(--accent2)");
}
function showNewStyle(){
 const c=CONFIG||{};
 document.getElementById("setContent").innerHTML=`
  <h3 style="margin-bottom:10px;font-size:14px;font-weight:700;color:var(--text)">新建风格</h3>
  <div class="mg"><label style="font-weight:600;color:var(--accent2);font-size:11px">📌 基础信息</label></div>
  <div class="mg"><label>风格名称 *</label><input id="ns_name" placeholder="如：赛博朋克都市"/></div>
  <div class="mg"><label>题材分类（逗号分隔）</label><input id="ns_cat" placeholder="废土, 赛博, 奇幻"/></div>
  <div class="mg" style="margin-top:8px"><label style="font-weight:600;color:var(--accent2);font-size:11px">🎨 画面描述</label></div>
  <div class="mg"><label>art_style（英文风格）</label><input id="ns_art" value="cinematic environment concept art, realistic render"/></div>
  <div class="mg"><label>base_positive（正向提示词）</label><input id="ns_pos" value="超广角大全景，低角度仰拍，纵深透视，大气透视，电影级布光，概念场景设计，写实渲染，8K"/></div>
  <div class="mg"><label>base_negative（负面提示词）</label><input id="ns_neg" value="卡通，二次元，鲜艳高饱和，干净崭新建筑，平光，畸变"/></div>
  <div class="mg" style="margin-top:8px"><label style="font-weight:600;color:var(--accent2);font-size:11px">🤖 AI 生成</label></div>
  <div class="mg"><label>AI主体生成指令</label><input id="ns_gen" value="生成一句20-30字的场景主体，包含地貌+建筑+空间位置"/></div>
  <div class="modal-acts" style="margin-top:12px;border-top:1px solid var(--border);padding-top:10px">
   <button class="btng btng-s" onclick="document.getElementById('setMod').classList.remove('show')">取消</button>
   <button class="btng btng-p" onclick="saveNewStyle()">创建风格</button>
  </div>`;
 document.getElementById("setMod").classList.add("show");
}
async function saveNewStyle(){
 const name=document.getElementById("ns_name").value.trim();
 if(!name){st("请填写风格名称","var(--warn)");return}
 const r=await api("/api/create_style",{
  style_name:name,
  category:document.getElementById("ns_cat").value||"自定义",
  art:document.getElementById("ns_art").value||"cinematic environment concept art",
  positive:document.getElementById("ns_pos").value||"超广角大全景",
  negative:document.getElementById("ns_neg").value||"卡通，二次元",
  gen_prompt:document.getElementById("ns_gen").value||"生成场景主体"
 });
 if(!r.ok){st("创建失败: "+(r.error||""),"var(--warn)");return}
 document.getElementById("setMod").classList.remove("show");
 // 刷新风格下拉
 const ri=await api("/api/init");
 if(ri.names){
  const sel=document.getElementById("styleSelect");
  sel.innerHTML=ri.names.map(n=>`<option value="${n}"${n==name?" selected":""}>${n}</option>`).join("");
  setStyle(name);
 }
 st("已创建: "+name,"var(--accent2)");
}
function saveAll(){CARDS.forEach((c,i)=>{if(c.img)saveImg(i)})}
async function setStyle(n){await api("/api/set_style",{name:n});st("已切换: "+n,"var(--accent2)")}

function showTab(t){
 document.getElementById("tabGen").className="tab"+(t=="gen"?" act":"");
 document.getElementById("tabLib").className="tab"+(t=="lib"?" act":"");
 document.getElementById("gwrap").style.display=t=="gen"?"block":"none";
 document.getElementById("gallery").className="gallery"+(t=="lib"?" show":"");
 if(t=="lib")loadGallery();
}

async function loadGallery(){
 const g=document.getElementById("gallery");g.innerHTML="<span style='color:var(--hint)'>加载中...</span>";
 try{
  const r=await api("/api/list_images");if(!r.ok||!r.images){g.innerHTML="<span style='color:var(--hint)'>暂无素材</span>";return}
  g.innerHTML="";
  r.images.forEach(img=>{
   const d=document.createElement("div");d.className="g-item";
   d.innerHTML=`<img src="${img.url}" onclick="event.stopPropagation();document.getElementById('zoomImg').src=this.src;document.getElementById('zoomLayer').classList.add('show')" />
<div class="g-info">
<div class="gl">${img.name}</div>
<div class="gp">${img.prompt||'（无描述词）'}</div>
<div><button class="btng btng-d" style="font-size:8px;padding:1px 6px;margin-top:2px" onclick="event.stopPropagation();reuseGallery('${img.name}')">复用</button></div>
</div>`;
   g.appendChild(d);
  });
 }catch(e){g.innerHTML="<span style='color:var(--hint)'>加载失败</span>"}
 const gc=document.getElementById("galleryCount");
 if(gc&&r.images)gc.textContent=r.images.length>0?`(${r.images.length})`:"";
}
function showSettings(){
 const c=CONFIG||{};document.getElementById("setContent").innerHTML=`
  <h3 style="margin-bottom:8px;font-size:13px">设置</h3>
  <div class="mg"><label style="font-weight:600;color:var(--accent2)">LLM（写灵感）</label></div>
  <div class="mg"><label>API Key</label><input id="s_llm_key" value="${c.llm_api_key||""}"/></div>
  <div class="mg"><label>Base URL</label><input id="s_llm_url" value="${c.llm_base_url||""}"/></div>
  <div class="mg"><label>模型</label><select id="s_llm_model"><option value="deepseek-v4-flash"${c.text_model=="deepseek-v4-flash"?" selected":""}>deepseek-v4-flash</option><option value="deepseek-chat"${c.text_model=="deepseek-chat"?" selected":""}>deepseek-chat</option></select></div>
  <div class="mg"><label style="font-weight:600;color:var(--accent2);margin-top:6px">出图（画图）</label></div>
  <div class="mg"><label>API Key</label><input id="s_img_key" value="${c.image_api_key||""}"/></div>
  <div class="mg"><label>Base URL</label><input id="s_img_url" value="${c.image_base_url||""}"/></div>
  <div class="mg"><label>模型</label><select id="s_img_model"><option value="gpt-image-2-official"${c.image_model=="gpt-image-2-official"?" selected":""}>gpt-image-2-official</option><option value="gpt-image-2-ext"${c.image_model=="gpt-image-2-ext"?" selected":""}>gpt-image-2-ext</option></select></div>
  <div class="modal-acts">
   <button class="btng btng-d" onclick="document.getElementById('setMod').classList.remove('show')">取消</button>
   <button class="btng btng-p" onclick="saveSet()">保存</button>
  </div>`;
 document.getElementById("setMod").classList.add("show");
}
async function saveSet(){
 CONFIG.llm_api_key=document.getElementById("s_llm_key").value;
 CONFIG.llm_base_url=document.getElementById("s_llm_url").value;
 CONFIG.text_model=document.getElementById("s_llm_model").value;
 CONFIG.image_api_key=document.getElementById("s_img_key").value;
 CONFIG.image_base_url=document.getElementById("s_img_url").value;
 CONFIG.image_model=document.getElementById("s_img_model").value;
 await api("/api/save_config",CONFIG);
 document.getElementById("setMod").classList.remove("show");st("已保存","var(--accent2)");
}
</script>
</body>
</html>"""

if __name__=="__main__":
    import webbrowser
    port=int(os.environ.get("PORT",8859))
    bind=os.environ.get("BIND","0.0.0.0")
    server=http.server.ThreadingHTTPServer((bind,port),Handler)
    print(f"[OK] 街灯AI--场景生成器 启动 http://{bind}:{port}")
    print(f"     http://127.0.0.1:{port}")
    webbrowser.open(f"http://127.0.0.1:{port}")
    try: server.serve_forever()
    except KeyboardInterrupt: print("\n已停止")
