"""
街灯AI--场景生成器 — 底部控制栏布局
"""
import os, sys, json, requests, base64, time, threading, re, glob, http.server
from datetime import datetime
from urllib.parse import urlparse

# PyInstaller兼容
if getattr(sys,'frozen',False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class Backend:
    def __init__(self):
        self.config = self._load_config()
    def _load_config(self):
        fp = os.path.join(BASE_DIR,"config.json")
        d = {"llm_api_key":"","llm_base_url":"https://api.deepseek.com","text_model":"deepseek-v4-flash",
             "image_api_key":"","image_base_url":"https://api.apimart.ai/v1","image_model":"gpt-image-2-official",
             "poll_interval":2000,"max_polls":60,"custom_suffix":"","keep_human":False}
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
    def _batch_dir(self):
        bd=os.path.join(BASE_DIR,"history","batches")
        os.makedirs(bd,exist_ok=True)
        return bd
    def _load_batches(self):
        bd=self._batch_dir();bs=[]
        for fn in sorted(os.listdir(bd),reverse=True):
            if fn.endswith(".json"):
                try:
                    with open(os.path.join(bd,fn),"r",encoding="utf-8") as f: bs.append(json.load(f))
                except: pass
        return bs
    def _new_batch(self,subject,descs):
        bid=datetime.now().strftime("%Y%m%d_%H%M%S")
        b={"id":bid,"subject":subject,"created":bid,"descriptions":descs,"images":[],"marketing":[]}
        bd=self._batch_dir()
        with open(os.path.join(bd,f"{bid}.json"),"w",encoding="utf-8") as f: json.dump(b,f,ensure_ascii=False,indent=2)
        return bid
    def _add_to_batch(self,bid,fname,prompt,desc_idx):
        bs=self._load_batches()
        for b in bs:
            if b["id"]==bid:
                b.setdefault("images",[]).append({"file":fname,"prompt":prompt,"desc_idx":desc_idx})
                b.setdefault("marketing",[])
                self._save_batch(b); return True
        return False
    def _save_batch(self,b):
        bd=self._batch_dir()
        with open(os.path.join(bd,f"{b['id']}.json"),"w",encoding="utf-8") as f: json.dump(b,f,ensure_ascii=False,indent=2)
    def save_config(self,c):
        self.config.update(c);
        with open(os.path.join(BASE_DIR,"config.json"),"w",encoding="utf-8") as f: json.dump(self.config,f,ensure_ascii=False,indent=2)
        return {"ok":True}
    def get_init(self):
        return {"config":{k:self.config[k] for k in ["llm_api_key","llm_base_url","text_model","image_api_key","image_base_url","image_model","custom_suffix","keep_human"]}}
    def gen_subject_ideas(self):
        try:
            import random as _idea_r
            _type=_idea_r.choice(["塔/尖塔/方尖碑","穹顶/半球体","拱桥/弧形拱","平台/悬浮台地","方碑/巨型立方体","巨门/门框结构","巨像/雕像","环形/圆环","棱柱/多面体","斜墙/倾斜平面"])
            _land=_idea_r.choice(["冰原","沙漠","云海","荒原","海岸悬崖","火山口","深海裂谷","城市废墟","地下空洞","盐碱地","冻土苔原","干涸河床","雾霭沼泽","迷雾峡谷","镜面盐湖","灰烬平原","寂静湖面","暮色荒滩","薄雾丘陵","苍白苔原"])
            prompt=f"""你作为宏大概念主体设计师。输出1个独特的巨型核心主体，20-40字。
格式：{_land} + {_type}结构体。

**形体底层逻辑：**
- 大几何优先，单一整块结构体，非零散拼接
- 层次来自空间凹凸（高低落差、悬挑、中空镂空），不是表面装饰
- 仅1种主材：磨砂金属/哑光混凝土/致密平滑岩体/半通透柔光晶体
- 轮廓简洁干净，无锯齿状繁杂外缘

**避坑：** 机械零件齿轮、废墟残骸、繁复雕花、有机扭曲造型、写实古建筑（东方元素只能抽象轮廓不可写实）

只输出一行，不要编号不要引号。"""
            h=self._headers("llm")
            p={"model":self.config.get("text_model","deepseek-v4-flash"),
               "messages":[{"role":"user","content":prompt}],
               "max_tokens":300,"temperature":0.9}
            r=requests.post(f"{self.config.get('llm_base_url','https://api.deepseek.com')}/chat/completions",headers=h,json=p,timeout=30)
            r.raise_for_status()
            txt=r.json()["choices"][0]["message"]["content"]
            lines=[l.strip().strip("\"'0123456789.、）) ") for l in txt.split("\n") if l.strip() and len(l.strip())>10]
            if not lines: return {"ok":False,"error":"无结果"}
            return {"ok":True,"ideas":lines[:5]}
        except Exception as e: return {"ok":False,"error":f"异常: {str(e)[:80]}"}
    def gen_desc(self,subject,count,rotate=False):
        if subject:
            ins=f"""基于核心主体「{subject}」生成{count}条场景描述，每行一条。

只写【核心主体+配套环境】，80-120字。不写镜头、不写画风、不写构图、不写人物、不写光影、不写画质——那些由出图系统统一添加。

主体构造准则：
- ⚠️ {count}条必须使用**完全一致的句式结构**（主语位置、修饰顺序、收尾方式相同），只轻微变化视角对应的环境细节
- ⚠️ {count}条必须使用**完全一致的美术画风**
- 大几何优先：球体/穹顶/圆环/棱柱/斜面方台/弧形拱，拒绝有机杂乱造型
- 单一整块巨型结构体，非零散拼接；层次来自空间凹凸（悬挑、中空、高低落差），不是表面装饰
- 仅1种主材：磨砂金属/哑光混凝土/致密平滑岩体，表面平整无裂纹苔藓锈迹
- 轮廓简洁干净，无锯齿繁杂外缘
- **东方元素规则（若主体含东方意象）：取轮廓形态，舍细碎构件——提炼抽象坡顶/重檐轮廓并完全简化，无斗拱、瓦片、雕花、木质结构、写实古建筑细节；可以有东方意境，不能有东方装饰；抽象化几何化，不要写实古建筑**
- 完整保留以下主体：{subject}
- **环境：根据地貌关键词自动匹配——主体含海/水→水体环境，含雪/冰→雪原，含沙/漠→荒漠，含林/草→草甸，含裂谷/山石→荒原，其他→云海。均质连续无零散杂物，远景融入雾气**
- 全程用中文"""
        else:
            ins=f"""创作{count}条场景描述，每行一条。

只写【核心主体+配套环境】，80-120字。不写镜头、不写画风、不写构图、不写人物、不写光影、不写画质——那些由出图系统统一添加。

主体构造准则：
- ⚠️ {count}条必须使用**完全一致的句式结构**（主语位置、修饰顺序、收尾方式相同），只轻微变化视角对应的环境细节
- ⚠️ {count}条必须使用**完全一致的美术画风**
- 大几何优先，单一整块巨型结构体，层次来自空间凹凸，非表面装饰
- 仅1种主材，表面平整无裂纹苔藓锈迹，轮廓简洁干净
- **东方意象（若含）：只能抽象轮廓不可写实古建，无斗拱瓦片雕花木质结构，取形态舍装饰**
- 自主创作宏大核心主体，单一核心不堆砌
- **环境：根据地貌关键词自动匹配——含海/水→水体，含雪/冰→雪原，含沙/漠→荒漠，含林/草→草甸，其他→云海/荒原。均质连续无零散杂物，远景融入雾气**
- 全程用中文"""
        try:
            h=self._headers("llm")
            p={"model":self.config.get("text_model","deepseek-v4-flash"),
               "messages":[{"role":"user","content":ins}],"max_tokens":1024,"temperature":0.6}
            r=requests.post(f"{self.config.get('llm_base_url','https://api.deepseek.com')}/chat/completions",headers=h,json=p,timeout=25)
            r.raise_for_status()
            txt=r.json()["choices"][0]["message"]["content"]
            lines=[l.strip().lstrip("0123456789.、）) ") for l in txt.split("\n") if l.strip() and len(l.strip())>30]
            lines=[l for l in lines if len(l)>30][:count]
            # 用build_prompt生成full prompt作为后备，同时把初稿作为desc
            prompts=[self.build_prompt(lines[i] if i<len(lines) else subject,False,False,self.config.get("keep_human",True),"1024x1792") for i in range(count)]
            batch_id=self._new_batch(subject or f"场景",lines[:count])
            # 自动生成故事文案
            try:
                poem_resp=self.gen_batch_poem(batch_id)
                poem=poem_resp.get("text","") if poem_resp.get("ok") else ""
            except: poem=""
            return {"ok":True,"descriptions":lines[:count],"prompts":prompts,"batch_id":batch_id,"poem":poem}
        except Exception as e: return {"ok":False,"error":f"LLM错误: {str(e)[:120]}"}
    def gen_one_desc(self):
        try:
            h=self._headers("llm")
            p={"model":self.config.get("text_model","deepseek-v4-flash"),
               "messages":[{"role":"user","content":"输出1个巨构场景描述，60-100字。只写【核心主体+环境】，不写镜头不写画风不写人物不写光影不写画质。大几何优先，单一整块结构体，均质自然基底环境无零散杂物。"}],
               "max_tokens":300,"temperature":0.8}
            r=requests.post(f"{self.config.get('llm_base_url','https://api.deepseek.com')}/chat/completions",headers=h,json=p,timeout=25)
            r.raise_for_status()
            txt=r.json()["choices"][0]["message"]["content"].strip().strip("\"'")
            raw=txt[:150] if len(txt)>150 else txt
            if len(raw)<20: raw="云海之上悬浮着一座倒置的磨砂金属巨塔，表面光滑无纹饰，中空结构贯穿三层"
            prompt=self.build_prompt(raw,False,False,self.config.get("keep_human",True),"1024x1792")
            return {"ok":True,"desc":raw,"prompt":prompt}
        except Exception as e: return {"ok":False,"error":f"LLM错误: {str(e)[:80]}"}
    def gen_marketing(self,subject,desc):
        # 保留兼容
        return self.gen_batch_poem_by_subject(subject,desc)
        try:
            h=self._headers("llm")
            p={"model":self.config.get("text_model","deepseek-v4-flash"),
               "messages":[{"role":"user","content":f"""为以下AI场景写一句像故事开头的话（10-20字），有叙事感和画面意境：

场景主体：{subject}
场景描述：{desc[:150]}

要求：
- 像小说或电影开篇第一句，引人入胜
- 可以有故事感、叙事张力
- 不要"震撼""史诗""宏大"等直白词
- **严格控制在10-20字**
- 只输出一句话，不要引号或解释"""}],
               "max_tokens":100,"temperature":0.8}
            r=requests.post(f"{self.config.get('llm_base_url','https://api.deepseek.com')}/chat/completions",headers=h,json=p,timeout=30)
            r.raise_for_status()
            txt=r.json()["choices"][0]["message"]["content"].strip().strip("\"'")
            return {"ok":True,"text":txt}
        except Exception as e: return {"ok":False,"error":str(e)[:80]}
    def gen_batch_poem(self,batch_id):
        try:
            bs=self._load_batches()
            b=None
            for bb in bs:
                if bb["id"]==batch_id: b=bb; break
            if not b: return {"ok":False,"error":"批次不存在"}
            subj=b.get("subject","未知场景")
            descs=b.get("descriptions",[])
            combined="；".join(descs[:3])[:300]
            h=self._headers("llm")
            p={"model":self.config.get("text_model","deepseek-v4-flash"),
               "messages":[{"role":"user","content":f"""为以下AI史诗场景写一句像故事开头的话（10-20字），有叙事感：

场景：{subj}
描述：{combined}

要求：
- 像小说或电影开篇第一句，引人入胜
- 有故事感、叙事张力，像要展开一段传奇
- 不要"震撼""史诗""宏大"等直白词
- **严格控制在10-20字**
- 只输出一句话，不要引号或解释"""}],
               "max_tokens":100,"temperature":0.8}
            r=requests.post(f"{self.config.get('llm_base_url','https://api.deepseek.com')}/chat/completions",headers=h,json=p,timeout=30)
            r.raise_for_status()
            poem=r.json()["choices"][0]["message"]["content"].strip().strip("\"'")
            # 保存到批次
            b["poem"]=poem
            self._save_batch(b)
            return {"ok":True,"text":poem}
        except Exception as e: return {"ok":False,"error":str(e)[:80]}
    def optimize_descs(self,descs,style=""):
        if not descs: return {"ok":False,"error":"无描述词"}
        try:
            h=self._headers("llm")
            txt="\n".join([f"{i+1}. {d}" for i,d in enumerate(descs)])
            p={"model":self.config.get("text_model","deepseek-v4-flash"),
               "messages":[{"role":"user","content":f"""你作为提示词智能优化引擎。读取以下{len(descs)}条原始正向提示词，识别并修复缺陷。

**核心红线（绝对遵守）：**
- **不新增任何原始文本不存在的物体、建筑、景观、环境元素**
- **不修改原有主体、场景基调**

**人物规则（自适应配置）：**
- 原文的人物描述一律删除，统一按以下规范重写
- 若原始无人物 → 结合场景氛围自主匹配风格统一的单人形象（如骑马/古风长袍/科幻战甲/探险装束等），放置画面下方远景，体型渺小，人物不能占据视觉中心
- 若原始已有人物 → 也统一删除重写为自适应风格形象
- 硬性限制：仅限单人，远景，不特写，不生成人群，不生成写实清晰五官

**优化逻辑（【第三步：智能重构二次精细化优化】）：**
1. 禁止随意增删核心画面元素
2. 镜头自由自适应，清除矛盾镜头参数，维持大面积留白
3. 构图自主选用平衡规整样式，杜绝失衡凌乱构图
4. 保留远景单人约束，仅限单人、禁止特写与人群
5. 理顺语句、剔除重复冗余词汇，强化宏大空灵氛围
6. 画面干净通透，单一主光源，剔除杂乱彩光；材质规避锈蚀、斑驳风化

**输出格式：**
[
  {{"prompt":"优化后的完整正向提示词","negative":"针对性补充的负面提示词"}},
  ...
]

【原始提示词】
{txt}

只输出JSON数组，不要多余文字"""}],
               "max_tokens":2048,"temperature":0.3}
            r=requests.post(f"{self.config.get('llm_base_url','https://api.deepseek.com')}/chat/completions",headers=h,json=p,timeout=25)
            r.raise_for_status()
            raw=r.json()["choices"][0]["message"]["content"]
            import re
            m=re.search(r'\[.*?\]',raw,re.DOTALL)
            optimized=[];negatives=[]
            if m:
                try:
                    data=json.loads(m.group())
                    for item in data:
                        optimized.append(item.get("prompt",""))
                        negatives.append(item.get("negative",""))
                except: pass
            if not optimized:
                # fallback: 如果JSON解析失败，尝试提取prompt字段
                prompts_raw=re.findall(r'"prompt"\s*:\s*"([^"]+)"',raw)
                if prompts_raw:
                    optimized=prompts_raw[:len(descs)]
                else:
                    lines=[l.strip() for l in raw.split("\n") if l.strip() and len(l)>20]
                    optimized=lines[:len(descs)]
            if not optimized:
                return {"ok":True,"optimized":descs,"negatives":[]}
            return {"ok":True,"optimized":optimized[:len(descs)],"negatives":negatives}
        except Exception as e: return {"ok":False,"error":f"优化异常: {str(e)[:80]}"}
    def build_prompt(self,desc,comp=False,light=False,human=True,size="1024x1792"):
        # 统一画风体系：不依赖风格文件
        d=desc.lower()
        if comp:
            comps=["轻微偏移中心构图，建筑偏左放置","俯仰角度微调，镜头略向下倾斜","水平线偏移，建筑偏右占据2/3画面","画面轻微旋转，增加不稳定感"]
            # 直接加进desc但不改变结构
            desc+=f"，{__import__('random').choice(comps)}"
        if light:
            lights=["晨雾浓度增加，光线更柔和","暮色更深，冷蓝色调为主","霞光增强，金色轮廓光更明显","阴沉天光，无直射光，漫反射为主","薄暮时分，天边残留微弱暖光"]
            desc+=f"，{__import__('random').choice(lights)}"
        # 场景分类：巨构式「虚无干净」vs 自然场景「有序干净」
        d=desc.lower()
        is_natural=any(w in d for w in ["森林","林","树","丛林","海岸","沙滩","海滩","古","中式","东方","庙","塔","宫","亭","阁","花","草","山"])
        is_underwater=any(w in d for w in ["水下","深海","海底","海下","水中","沉没"])
        if is_underwater: is_natural=False
        # 通用正向固定骨架
        skeleton="24-28mm广角，三分构图，预留大面积留白空间，无近距离杂乱前景，影视概念渲染，低纹理密度，材质完整，柔和物理光照，单一光源，少量环境元素，剔除多余细碎物体，低饱和统一色调，8K，画面通透干净"
        # ① 镜头语言：三大视角循环 + 两种构图自适应
        import random as _lens_r
        angle=_lens_r.choice(["低角度仰拍","45度斜向俯视","高空远景平视"])
        # 环形/对称/穹顶类主体优先对称构图，其余三分法偏移
        if any(w in d for w in ["对称","居中","中心","环形","圆形","穹顶","拱门","圆"]):
            comp=_lens_r.choice(["准对称居中构图，主体位于画面中轴线","准对称居中构图，轻微非对称偏移防止僵硬"])
        else:
            comp=_lens_r.choice(["三分法偏移构图，主体位于画面一侧，另一侧大面积留白","准对称居中构图，主体位于中轴线"])
        lens=f"24-35mm广角镜头，{angle}，{comp}，干净两点透视，预留大面积留白空间（画面40%-65%空白），无近距离前景遮挡，深景深，全域清晰，画面层次仅三层：稀薄前景→中景主体→远景朦胧环境"
        # ② 画风标签
        if is_natural:
            style_tag="3A开放世界游戏环境CG静帧质感，PBR三维渲染，适度美术概括降低照片级写实程度，主动精简微观细碎纹理光影柔和压缩，统一大气体积雾画面拥有柔和色块过渡，无油画笔触无厚涂手绘肌理，杜绝极致照片写实，低纹理密度哑光平滑材质，自然光线柔和过渡，低饱和度统一色调，画面干净克制"
        else:
            style_tag="3A开放世界游戏环境CG静帧质感，PBR三维渲染，适度美术概括降低照片级写实程度，主动精简微观细碎纹理光影柔和压缩，统一大气体积雾画面拥有柔和色块过渡，无油画笔触无厚涂手绘肌理，杜绝极致照片写实，低纹理密度哑光平滑材质，无表面雕花无密集孔洞无外挂零件，单一柔和漫射天光，低饱和度统一色调，画面拥有无限延伸感——环境边界渐变虚化消融于雾霭，无硬质隔断，辽阔静谧超然孤寂，巨构独立于自然体系互不交融，排斥丰富生态生机场景，画面干净克制"
        # ③ 核心主体 从 desc 来
        # ④ 场景自适应环境 — 柔和弥散、边界渐变的均质自然基底
        # 注意：地貌类关键词优先于水体类，避免"深海裂谷"被误判为水下
        if any(w in d for w in ["荒漠","沙漠","沙","戈壁","干旱","裂谷"]):
            env="，主体立于无垠荒漠之上，平整地面向远方渐变，地平线隐入薄雾"
        elif any(w in d for w in ["雪原","冰原","冻土","苔原"]):
            env="，主体立于无垠雪原之上，雪地平整向远方渐变，地平线消融于灰白雾霭中"
        elif any(w in d for w in ["森林","林","树","丛林","密林","林地","草甸","草地","草原"]):
            env="，主体立于平缓均质草甸之上，远方雾霭弥漫，远景渐溶于雾气之中"
        elif any(w in d for w in ["水下","深海","海底","海下","水中","沉没"]):
            env="，主体悬浮于渐变通透海水中，水体自上而下由亮转暗，远处幽光弥散，无边界感"
        elif any(w in d for w in ["海","海洋","海岸","沙滩","海滩","礁石","浪"]):
            env="，主体矗立于平静海面边缘，宽阔水体向远处渐变为雾霭，海平线消融于天光中"
        elif any(w in d for w in ["室内","房间","大厅","走廊","殿","堂","厅","馆"]):
            env="，主体置于空旷宏大室内，大面积纯色墙面与平整地面形成均质背景，空间边界隐约消融"
        elif any(w in d for w in ["城市","都市","赛博","霓虹","街道","高楼"]):
            env="，主体耸立于空旷城市中，平整路面向远处延伸渐变，建筑轮廓隐入雾霭"
        elif any(w in d for w in ["古","中式","东方","庙","塔","宫","殿","亭","阁"]):
            env="，主体取东方抽象轮廓，提炼重檐/坡顶几何形态并完全简化，哑光岩体完整连续，大面积薄雾留白，远景融入雾气"
        else:
            env="，主体悬浮于云海之上，纯净渐变天空向远方过渡，空旷大地隐入薄雾"
        # 均质基底统一收尾 — 无限延伸感：边界渐变虚化，无硬性隔断
        env+="，远景边界渐变虚化向远方缓缓消融于雾霭，无硬质地平线无山崖林木隔断，空间无限延伸没有终点"
        # ⑤ 人物策略：原文已有人物（AI优化后）则不追加
        neg_human=""
        has_char=any(w in desc for w in ["人影","剪影","人物","行人","身影","背影","骑手","人","女","男","战士","骑","袍","甲","衣","帽","剑","弓","探险","装束"])
        if has_char:
            pass  # AI优化已处理人物，trust it
        elif human:
            env+=f"，画面底部边缘下三分区域仅1个渺小人类黑色剪影，背对镜头眺望主体，体型极其微小，无面部细节无服饰特征，仅作尺度标尺，不遮挡主体轮廓，不吸引视线"
            neg_human="，无清晰人脸，无精致服饰细节，无人群聚集，无行人，无人物近景特写，无人物占据画面中心，无彩色杂乱服装"
        else:
            env+=f"，空无一人，无人类，无人影，不存在任何人物剪影，无行人，无生命体"
            neg_human="，无人类，无行人，无人影，无人物剪影，无单人，无多人，无站立人影，无远处人影，无生命体"
        # ⑥ 光影色彩
        light_color="单侧柔和漫射光，单一光源，无杂乱多重光斑，低饱和统一色调，色彩克制，整体色调协调统一，均匀通透光线，无强烈硬阴影，无死黑死角"
        # ⑦ 画质+光学
        quality="8K超写实渲染，细腻干净纹理，画面通透，电影级渲染，柔和光学效果，无杂乱眩光，无零散星芒，无色散"
        # 组装完整prompt：desc + 所有模块
        p=desc
        p+=f"，{lens}，{style_tag}，{env}，{light_color}，{quality}"
        # 通用基础负面词
        neg_base="，无杂乱碎片，无零散杂物，无密集植被，无过多人群，无飞鸟，无杂乱眩光，无彩色杂光斑，无锈蚀破损，无噪点，无拥挤构图，无手绘厚涂，无二次元动漫风格，无胶片粗颗粒，无风化废墟，无雕刻细节，无密集管线，无斑驳纹理"
        if is_natural:
            p+=f"{neg_base}{neg_human}"
        else:
            p+=f"{neg_base}{neg_human}，no deformed buildings, no clutter, no crowds, no vehicles, no birds, no trees, no billboards, no graffiti, no text, no watermark, no lens flare, no overexposure, no dead black shadows, no cartoon style, no oversaturated colors, no debris, no noise, no messy foreground, no hand painted, no thick paint, no cel shading, no sketch lines, no rough metal, no muddy ground, no moss, no cracks, no rust, no wear and tear"
        # 标注画幅尺寸
        size_map={"1024x1024":"方形构图1:1","1792x1024":"横屏宽幅16:9","1024x1792":"竖屏9:16","1344x768":"宽屏"}
        sn=size_map.get(size,"")
        if sn: p+=f"，{sn}"
        sfx=self.config.get("custom_suffix","")
        if sfx: p+=f", {sfx}"
        return p
    def generate(self,desc="",comp=False,light=False,size="1024x1792",prompt="",human=True,batch_id="",desc_idx=0):
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
                                # 加入批次
                                if batch_id:
                                    self._add_to_batch(batch_id,f"{ts}.png",prompt,desc_idx)
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
        import urllib.parse
        for part in ck.split(";"):
            part=part.strip()
            if part.startswith("token="):
                return urllib.parse.unquote(part[6:])==AUTH_TOKEN
        return False
    def _login_page(self):
        self.send_response(200);self.send_header("Content-Type","text/html;charset=utf-8");self.end_headers()
        self.wfile.write(f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>街灯AI JAYDEN AI</title>
<style>
body{{font-family:system-ui;background:#0f0f13;color:#e8e8ed;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}}
.box{{background:#18181c;border:1px solid #333;border-radius:12px;padding:40px;width:340px;text-align:center}}
.box h2{{margin-bottom:20px;font-size:18px;color:var(--accent2);}}
.box input{{width:100%;padding:10px;border:1px solid #333;border-radius:6px;background:#222;color:#e8e8ed;font-size:14px;outline:none;margin-bottom:16px;box-sizing:border-box}}
.box button{{width:100%;padding:10px;border:none;border-radius:6px;background:#6c5ce7;color:#fff;font-size:14px;cursor:pointer}}
.box button:hover{{background:#5a4bd1}}
.box .err{{color:#e17055;font-size:13px;margin-bottom:10px}}
</style></head><body><div class="bg-mid3"></div><div class="watermark">JAYDEN AI</div>
<div class="box"><h2>🔐 JaydenAI</h2>
<form method="post" action="/">
<input type="password" name="token" placeholder="输入访问密码" autofocus/>
<button type="submit">进入</button>
</form></div></body></html>""".encode())
    def do_GET(self):
        if self.path.startswith("/api/"):
            if not self._check_auth():
                self._json({"ok":False,"error":"未授权"}); return
        elif not self._check_auth():
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
        elif self.path=="/api/list_batches": self._json({"ok":True,"batches":backend._load_batches()})
        else: self.send_error(404)
    def do_POST(self):
        if self.path=="/":
            length=int(self.headers.get("Content-Length",0))
            body=self.rfile.read(length).decode() if length else ""
            import urllib.parse
            params=urllib.parse.parse_qs(body)
            tk=params.get("token",[None])[0]
            if tk==AUTH_TOKEN:
                self.send_response(302);self.send_header("Set-Cookie",f"token={AUTH_TOKEN}; Path=/; Max-Age=86400; SameSite=Lax");self.send_header("Location","/");self.end_headers()
            else:
                self.send_response(200);self.send_header("Content-Type","text/html;charset=utf-8");self.end_headers()
                self.wfile.write(f"""<!DOCTYPE html><html><body style="background:#0f0f13;color:#e8e8ed;display:flex;align-items:center;justify-content:center;height:100vh;font-family:system-ui"><div style="text-align:center"><p style="color:#e17055;margin-bottom:16px">❌ 密码错误</p><a href="/" style="color:#6c5ce7">重新输入</a></div></body></html>""".encode())
            return
        if AUTH_TOKEN and not self._check_auth():
            self._json({"ok":False,"error":"未授权"}); return
        length=int(self.headers.get("Content-Length",0))
        body=self.rfile.read(length).decode() if length else ""
        data=json.loads(body) if body else {}
        p=urlparse(self.path).path;resp={"ok":False}
        try:
            if p=="/api/gen_desc": resp=backend.gen_desc(data.get("subject",""),int(data.get("count",3)))
            elif p=="/api/gen_ideas": resp=backend.gen_subject_ideas()
            elif p=="/api/gen_one": resp=backend.gen_one_desc()
            elif p=="/api/optimize": resp=backend.optimize_descs(data.get("descriptions",[]),data.get("style",""))
            elif p=="/api/generate": resp=backend.generate(data.get("desc",""),data.get("comp",False),data.get("light",False),data.get("size","1024x1792"),data.get("prompt",""),data.get("human",True),data.get("batch_id",""),int(data.get("desc_idx",0)))
            elif p=="/api/save_config": resp=backend.save_config(data)
            elif p=="/api/gen_marketing": resp=backend.gen_marketing(data.get("subject",""),data.get("desc",""))
            elif p=="/api/gen_batch_poem": resp=backend.gen_batch_poem(data.get("batch_id",""))
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
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<title>街灯AI JAYDEN AI</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter','Segoe UI',system-ui,sans-serif;background:#0f0f13;color:#e8e8ed;height:100vh;display:flex;flex-direction:column;font-size:14px;position:relative;overflow:hidden}
/* 背景动态渐变光晕 */
body::before{content:'';position:fixed;top:-30%;left:-15%;width:80%;height:80%;background:radial-gradient(ellipse at 30% 20%,rgba(108,92,231,.18) 0%,rgba(108,92,231,.06) 40%,transparent 70%);animation:dGlow 10s ease-in-out infinite alternate;pointer-events:none;z-index:0}
body::after{content:'';position:fixed;bottom:-25%;right:-10%;width:60%;height:60%;background:radial-gradient(ellipse at 70% 80%,rgba(0,206,201,.14) 0%,rgba(6,182,212,.05) 40%,transparent 70%);animation:dGlow2 14s ease-in-out infinite alternate;pointer-events:none;z-index:0}
/* 第三层中部暖色光晕 */
.bg-mid3{position:fixed;top:40%;left:50%;transform:translate(-50%,-50%);width:50%;height:40%;background:radial-gradient(ellipse at center,rgba(255,200,100,.06) 0%,transparent 60%);animation:dGlow3 18s ease-in-out infinite alternate;pointer-events:none;z-index:0}
.watermark{position:fixed;bottom:0;left:0;right:0;text-align:center;padding:8px 0 12px;font-size:11px;font-weight:600;letter-spacing:3px;color:rgba(108,92,231,.15);pointer-events:none;z-index:0;user-select:none}
@keyframes dGlow{0%{transform:translate(0,0) scale(1)}100%{transform:translate(8%,6%) scale(1.25)}}
@keyframes dGlow2{0%{transform:translate(0,0) scale(1)}100%{transform:translate(-6%,-4%) scale(1.2)}}
@keyframes dGlow3{0%{opacity:.5;transform:translate(-50%,-50%) scale(1)}100%{opacity:1;transform:translate(-50%,-50%) scale(1.15)}}
:root{--bg:#0f0f13;--card:#18181c;--surf:#22222a;--input:#2a2a32;--border:#33333d;--accent:#6c5ce7;--accent2:#00cec9;--warn:#e17055;--text:#e8e8ed;--body:#b0b0b8;--hint:#6a6a74}
.header{display:flex;align-items:center;padding:16px 20px;gap:16px;background:linear-gradient(135deg,#141420 0%,#1a1a30 50%,#141420 100%);border-bottom:1px solid rgba(51,51,61,.5);flex-shrink:0;position:relative;z-index:1}
.header::after{content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent 0%,rgba(108,92,231,.04) 50%,transparent 100%);pointer-events:none}
.header h1{font-size:18px;font-weight:700;background:linear-gradient(135deg,#a29bfe,#6c5ce7 30%,#00cec9 70%,#55efc4);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;flex-shrink:0}
.header select{background:var(--surf);color:var(--text);border:1px solid var(--border);border-radius:5px;padding:5px 10px;font-size:13px;outline:none;cursor:pointer}
.header .tab{background:none;border:none;color:var(--hint);font-size:13px;cursor:pointer;padding:5px 12px;border-radius:4px;font-weight:600}
.header .tab:hover{color:var(--text);background:var(--surf)}
.header .tab.act{color:var(--accent2);background:linear-gradient(135deg,rgba(108,92,231,.15),rgba(0,206,201,.1))}
.tbar{display:flex;align-items:center;gap:8px;padding:4px 16px;background:rgba(34,34,42,.55);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);font-size:12px;color:var(--hint);flex-shrink:0;min-height:30px;position:relative;z-index:1;border-bottom:1px solid rgba(51,51,61,.3)}
.gallery{display:none;padding:12px 16px;flex:1;overflow-y:auto}
.gallery.show{display:block}
.gallery .g-item{display:flex;margin:0 0 10px 0;background:var(--card);border-radius:8px;border:1px solid var(--border);overflow:hidden;cursor:pointer;gap:0}
.gallery .g-item:hover{border-color:var(--accent)}
.gallery .g-item img{width:160px;height:auto;max-height:120px;object-fit:contain;flex-shrink:0;cursor:zoom-in}
.gallery .g-item .g-info{flex:1;padding:8px 10px;overflow:hidden;display:flex;flex-direction:column;gap:4px}
.gallery .g-item .gl{font-size:10px;color:var(--hint);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gallery .g-item .gp{font-size:11px;color:var(--body);line-height:1.5;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
/* 批次图库 */
.g-batch{margin:0 0 16px 0;background:var(--card);border-radius:10px;border:1px solid var(--border);overflow:hidden}
.g-batch-hd{display:flex;align-items:center;gap:8px;padding:12px 14px;cursor:pointer;user-select:none}
.g-batch-hd:hover{background:var(--surf)}
.g-batch-subj{font-size:15px;font-weight:700;color:var(--accent2);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.g-batch-meta{font-size:11px;color:var(--hint);white-space:nowrap}
.g-batch-expand{font-size:11px;color:var(--hint);transition:transform .2s}
.g-batch-body{display:none;padding:10px 14px 14px;border-top:1px solid var(--border)}
.g-batch-body.show{display:block}
.g-batch-poem{font-size:13px;color:var(--text);font-style:italic;padding:8px 14px;text-align:center;border-bottom:1px solid var(--border);line-height:1.7;background:rgba(108,92,231,.04)}
.g-batch-txt{font-size:9px;color:var(--hint);padding:2px 0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.g-batch-poem{width:100%;font-size:12px;color:var(--accent2);font-style:italic;padding:6px 0;text-align:center;border-bottom:1px solid var(--border);margin-bottom:6px;line-height:1.6}
/* 图库工具栏 */
.g-toolbar{display:flex;align-items:center;gap:6px;margin-bottom:8px;flex-wrap:wrap}
.g-toolbar input{flex:1;min-width:120px;background:var(--input);border:1px solid var(--border);border-radius:5px;padding:5px 8px;font-size:12px;color:var(--text);outline:none}
.g-toolbar input:focus{border-color:var(--accent)}
/* 卡片式图库 */
.g-batch-card{display:flex;gap:8px;background:var(--card);border-radius:6px;border:1px solid var(--border);overflow:hidden;margin-bottom:6px;break-inside:avoid}
.g-batch-card:hover{border-color:var(--accent)}
.g-batch-card.folded .g-batch-desc{display:none}
.g-batch-card.folded img{opacity:.5}
.g-batch-card img{width:120px;height:auto;max-height:90px;object-fit:contain;flex-shrink:0;cursor:zoom-in}
.g-batch-info{flex:1;padding:6px 8px;display:flex;flex-direction:column;gap:3px;overflow:hidden}
.g-batch-idx{font-size:9px;color:var(--hint);font-weight:600}
.g-batch-desc{font-size:11px;color:var(--body);line-height:1.5;overflow:hidden;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical}
/* 瀑布流布局 */
.g-batch-body{display:none;padding:6px 10px 10px;border-top:1px solid var(--border)}
.g-batch-body.show{display:block;column-count:4;column-gap:10px}
@media(max-width:1200px){.g-batch-body.show{column-count:3}}
@media(max-width:900px){.g-batch-body.show{column-count:2}}
@media(max-width:600px){.g-batch-body.show{column-count:1}.g-batch-card{flex-direction:row}.g-batch-card img{width:90px;height:70px}.g-batch-desc{font-size:10px;-webkit-line-clamp:2}}
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
.zoom-nav{position:absolute;top:50%;transform:translateY(-50%);font-size:32px;color:#fff;cursor:pointer;z-index:10;opacity:.4;padding:12px;text-shadow:0 1px 4px rgba(0,0,0,.5);transition:opacity .2s;user-select:none}
.zoom-nav:hover{opacity:.9}.zoom-prev{left:8px}.zoom-next{right:8px}
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
.btng-i{background:linear-gradient(135deg,#00b894,#55efc4);color:#fff}
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
.header{padding:8px 10px;gap:6px;flex-wrap:wrap;justify-content:flex-start}.header h1{font-size:17px!important;text-align:left;margin-bottom:2px}
.header .tab{font-size:11px;padding:4px 8px}
.header .btng{font-size:9px!important;padding:2px 5px!important}
.grid{grid-template-columns:1fr!important;gap:8px}
.card{padding:8px}.card .desc{font-size:12px}.card .acts{gap:3px}
.card .btng{font-size:10px!important;padding:3px 8px!important}
/* 底部主按钮：灵感 & 批量生成 手机放大 */
.bbar .btng{font-size:11px!important;padding:6px 14px!important}
.bbar .btng-p,.bbar .btng-d{min-width:72px}
.gwrap{padding:8px 8px 120px}.gallery{padding:8px}
.g-batch{margin:0 0 10px}.g-batch-hd{padding:8px 10px}.g-batch-body{padding:6px 8px 10px}
.g-batch-body.show{column-count:1!important}.g-batch-subj{font-size:13px}
.g-batch-card img{width:80px;height:60px}.g-batch-info{padding:4px 6px}
.g-batch-desc{font-size:10px;-webkit-line-clamp:2}.g-batch-meta{font-size:9px}
.g-batch-poem{font-size:11px;padding:6px 10px}
.bar{flex-wrap:wrap;gap:4px;padding:6px 8px;justify-content:center}
.bar .btng{font-size:10px!important;padding:3px 8px!important}
.bbar{bottom:8px}
.bbar-main{flex-wrap:wrap;gap:5px;padding:8px 10px;width:96vw;justify-content:center}
.bbar-main input{width:100%!important;font-size:14px!important;padding:8px 10px!important}
.bbar-main .cnt{width:50px!important;min-width:50px!important}
.bbar select{font-size:12px!important;padding:6px 8px!important}
.bbar-adjacent{padding:10px 12px;width:96vw}.bbar-adjacent .row{gap:4px}
.bbar-adjacent .row input{width:100%!important;font-size:13px!important;padding:6px 8px!important}
.bbar-adjacent .chip{font-size:10px!important;padding:3px 7px!important}
#advBtn{display:none!important}
.modal-c{width:92vw!important;max-height:90vh;padding:14px}
.g-toolbar{flex-wrap:wrap}.g-toolbar input{min-width:80px;font-size:12px}
/* 缩放导航 */
.zoom-nav{font-size:24px;padding:8px}
.zoom-prev{left:2px}.zoom-next{right:2px}
}
</style>
</head>
<body>
<div class="header">
 <div style="display:flex;flex-direction:column;line-height:1.2;flex-shrink:0">
  <h1 style="margin:0;font-size:22px;font-weight:700;line-height:1;background:linear-gradient(135deg,#a29bfe,#6c5ce7 30%,#00cec9 70%,#55efc4);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text">街灯AI</h1>
  <span style="font-size:9px;color:var(--hint);font-weight:400;letter-spacing:1px">Created by Jayden</span>
 </div>
 <div style="flex:1"></div>
 <button class="tab act" onclick="showTab('gen')" id="tabGen">生成</button>
 <button class="tab" onclick="showTab('lib')" id="tabLib">图库 <span id="galleryCount" style="font-size:9px;color:var(--accent2)"></span></button>
 <button class="btng btng-d" onclick="showSettings()" style="font-size:11px;padding:3px 10px">端口</button>
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
  <button class="btng btng-i" onclick="genIdeas()" id="ideaBtn">生成灵感</button>
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
  </div>
 </div>
</div>

<div id="setMod" class="modal"><div class="modal-c" id="setContent"></div></div>
<div class="zoom-layer" id="zoomLayer" onclick="if(event.target===this)closeZoom()">
 <span style="position:absolute;top:12px;right:16px;font-size:22px;color:#fff;cursor:pointer;z-index:10;opacity:.7;text-shadow:0 1px 3px rgba(0,0,0,.5);" onclick="closeZoom()">&times;</span>
 <span class="zoom-nav zoom-prev" onclick="zoomNav(-1);event.stopPropagation()">&#10094;</span>
 <span class="zoom-nav zoom-next" onclick="zoomNav(1);event.stopPropagation()">&#10095;</span>
 <img id="zoomImg" src="" alt="放大预览" onclick="event.stopPropagation()"/>
 <div id="zoomDesc" style="position:absolute;bottom:0;left:0;right:0;padding:14px 20px;background:linear-gradient(transparent,rgba(0,0,0,.85));color:#e8e8ed;font-size:13px;line-height:1.7;text-align:center;max-height:35%;overflow-y:auto;pointer-events:none"></div>
</div>

<script>
let CARDS=[],CONFIG={},COMP=false,LIGHT=false,HUMAN=true;
async function api(path,data){
 const r=await fetch(path,{method:data?"POST":"GET",headers:{"Content-Type":"application/json"},credentials:"include",body:data?JSON.stringify(data):null});
 const ct=r.headers.get("content-type")||"";
 if(!ct.includes("json")){const txt=await r.text();throw new Error(txt.slice(0,80))}
 const j=await r.json();return j}
async function init(){
 const r=await api("/api/init");CONFIG=r.config||{};
 // 回填后缀
 const si=document.getElementById("sfxInp");
 if(CONFIG.custom_suffix){si.value=CONFIG.custom_suffix}
 HUMAN=CONFIG.keep_human!==false;
 // 加载图库数量
 try{const g=await api("/api/list_images");const gc=document.getElementById("galleryCount");if(gc&&g.images){gc.textContent=g.images.length>0?`(${g.images.length})`:""}}catch(e){}
}init();
function st(msg,c){document.getElementById("tbar").innerHTML=`<span style="color:${c||'var(--hint)'}">${msg}</span>`}

function toggleComp(){COMP=!COMP;document.getElementById("compBtn").style.borderColor=COMP?"var(--accent)":"var(--border)";document.getElementById("compBtn").style.color=COMP?"var(--accent)":"var(--hint)"}
function toggleLight(){LIGHT=!LIGHT;document.getElementById("lightBtn").style.borderColor=LIGHT?"var(--accent2)":"var(--border)";document.getElementById("lightBtn").style.color=LIGHT?"var(--accent2)":"var(--hint)"}
function toggleAdv(){const p=document.getElementById("advPanel");const b=document.getElementById("advBtn");p.classList.toggle("show");b.textContent=p.classList.contains("show")?"⚙收起":"⚙高级";}
function toggleHuman(){
}// 剪影按钮已移除，AI优化已自动带人
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
  document.getElementById("toggle"+i).textContent="▼";
 }else{
  el.textContent=CARDS[i].prompt;
  document.getElementById("toggle"+i).textContent="▲";
 }
}
async function genIdeas(){
 const btn=document.getElementById("ideaBtn");btn.disabled=true;btn.innerHTML='<span class="loading"></span>';
 try{
  const r=await api("/api/gen_ideas",{});
  if(!r.ok){st("灵感失败: "+(r.error||"无返回"),"var(--warn)");btn.disabled=false;btn.innerHTML="生成灵感";return}
  if(!r.ideas||!r.ideas.length){st("灵感失败: AI返回为空","var(--warn)");btn.disabled=false;btn.innerHTML="生成灵感";return}
  document.getElementById("subjInp").value=r.ideas[Math.floor(Math.random()*r.ideas.length)];
  st("灵感已填入","var(--accent2)");
 }catch(e){
  console.error("genIdeas error:",e);
  st("请求出错: "+e.message,"var(--warn)")
 }
 btn.disabled=false;btn.innerHTML="生成灵感";
}

 async function batchGen(){
 try{
 const subj=document.getElementById("subjInp").value.trim();
 const cnt=parseInt(document.getElementById("cntInp").value)||5;
 const btn=document.getElementById("genBtn");btn.disabled=true;btn.innerHTML='<span class="loading"></span>';
 st("生成描述词...","var(--accent)");
 const r=await api("/api/gen_desc",{subject:subj,count:cnt});
 btn.disabled=false;btn.innerHTML="批量生成";
 if(!r.ok){st("失败: "+r.error,"var(--warn)");return}
 if(!r.descriptions||r.descriptions.length==0){st("无结果","var(--warn)");return}
 const grid=document.getElementById("cardGrid");
 grid.innerHTML="";CARDS=[];
 r.descriptions.forEach((d,i)=>{
  const fp=r.prompts?.[i]||d;
  CARDS.push({desc:d,img:null,prompt:fp,batchId:r.batch_id||"",descIdx:i,optimized:false});
  const c=document.createElement("div");c.className="card";
  c.innerHTML=`<div class="idx">#${i+1}
   <span style="float:right;font-size:10px;color:var(--accent2);cursor:pointer" onclick="togglePrompt(${i})" id="toggle${i}">▼</span></div>
   <div class="desc" id="desc${i}" ondblclick="editDesc(${i})">${d}</div>
   <div class="acts">
    <button class="btng btng-p" style="font-size:12px;padding:5px 12px" onclick="genImg(${i})">开始生图</button>
    <button class="btng btng-s" style="font-size:12px;padding:5px 12px" onclick="redoDesc(${i})">重新描述</button>
    <button class="btng btng-d hidden" style="font-size:9px;padding:2px 6px" id="save${i}" onclick="saveImg(${i})">保存</button>
   </div>
   <div class="prev" id="prev${i}"><span class="ph">等待生图...</span></div>
   <div class="card-tags" id="tags${i}">
    <span id="optTag${i}" style="display:none;color:var(--accent2);font-size:9px">✦ 已优化</span>
    <span>📐${document.getElementById('sizeSelect')?.value||'9:16'}</span>
   </div>
  `;
  grid.appendChild(c);
 });
 const bar=document.getElementById("batchBar");bar.classList.remove("hidden");
 bar.innerHTML=`<button class="btng btng-p" style="font-size:13px;padding:6px 16px" onclick="genAll()">全部生图</button>
  <button class="btng btng-i" style="font-size:13px;padding:6px 16px" onclick="saveAll()">批量保存</button>
  <button class="btng btng-d" style="font-size:13px;padding:6px 16px;background:linear-gradient(135deg,#e17055,#fdcb6e);color:#fff" onclick="optimizeAll()">AI优化</button>
  <button class="btng btng-s" style="font-size:13px;padding:6px 16px;background:var(--accent2);color:#fff;border:none" onclick="redoAll()">全部重写</button>
  <span style="font-size:9px;color:var(--hint);margin-left:auto">双击描述词可编辑</span>`;
 st(`已生成 ${r.descriptions.length} 条`,"var(--accent2)");
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
 if(btns&&btns[1]){btns[1].disabled=false;btns[1].innerHTML="重新描述"}
 if(!r.ok)return;
 CARDS[i].desc=r.desc;CARDS[i].prompt=r.prompt||r.desc;CARDS[i].optimized=false;
 document.getElementById("desc"+i).textContent=document.getElementById("toggle"+i)?.textContent=="▲"?r.prompt||r.desc:r.desc;
 document.getElementById("prev"+i).innerHTML='<span class="ph">等待生图...</span>';
 document.getElementById("save"+i).classList.add("hidden");
 const ot=document.getElementById("optTag"+i);if(ot)ot.style.display="none";
 st("已更新","var(--accent2)");
}
async function redoAll(){
 const btn=document.querySelector("#batchBar .btng-d");if(btn){btn.disabled=true;btn.innerHTML='<span class="loading"></span>'}
 for(let i=0;i<CARDS.length;i++){
  const r=await api("/api/gen_one");
  if(r.ok){
   CARDS[i].desc=r.desc;CARDS[i].prompt=r.prompt||r.desc;CARDS[i].optimized=false;
   document.getElementById("desc"+i).textContent=r.desc;
   document.getElementById("prev"+i).innerHTML='<span class="ph">等待生图...</span>';
   document.getElementById("save"+i).classList.add("hidden");
   const ot=document.getElementById("optTag"+i);if(ot)ot.style.display="none";
  }
 }
 if(btn){btn.disabled=false;btn.innerHTML="全部重写"}
 st("全部已更新","var(--accent2)");
}
async function optimizeAll(){
 const btn=document.querySelector("#batchBar .btng-d:nth-child(3)");
 if(btn){btn.disabled=true;btn.innerHTML='<span class="loading"></span>'}
 st("智能优化Prompt中...","var(--accent)");
 const descs=CARDS.map(c=>c.prompt||c.desc);
 const r=await api("/api/optimize",{descriptions:descs});
 if(btn){btn.disabled=false;btn.innerHTML="AI优化"}
 if(!r.ok||!r.optimized){st("优化失败: "+(r.error||"未知"),"var(--warn)");return}
 for(let i=0;i<r.optimized.length&&i<CARDS.length;i++){
  const full=r.optimized[i];
  const short=full.length>80?full.slice(0,77)+'...':full;
  CARDS[i].desc=short;CARDS[i].prompt=full;CARDS[i].optimized=true;
  document.getElementById("desc"+i).textContent=short;
  const ot=document.getElementById("optTag"+i);
  if(ot)ot.style.display="inline";
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
  const raw=await fetch("/api/generate",{method:"POST",headers:{"Content-Type":"application/json"},credentials:"include",body:JSON.stringify({desc:CARDS[i].desc,prompt:CARDS[i].prompt||CARDS[i].desc,comp:COMP,light:LIGHT,size:sz,human:HUMAN,batch_id:CARDS[i].batchId||"",desc_idx:CARDS[i].descIdx||i})});
  const txt=await raw.text();console.log("genImg raw:",txt);
  let r;
  try{r=JSON.parse(txt)}catch(e){st("生图异常: 返回非JSON: "+txt.slice(0,80),"var(--warn)");if(btn){btn.disabled=false;btn.innerHTML="开始生图"}return}
  if(btn){btn.disabled=false;btn.innerHTML="开始生图"}
  if(!r.ok||!r.b64){st("生图失败: "+(r.error||"无法解析错误"),"var(--warn)");return}
  document.getElementById("prev"+i).innerHTML=`<img src="data:image/png;base64,${r.b64}" onclick="zoomImg(${i})" />`;
  CARDS[i].img=r.b64;document.getElementById("save"+i).classList.remove("hidden");
  document.querySelectorAll(".card")[i]?.classList.add("has-img");
  st("完成","var(--accent2)");
 }catch(e){console.error("genImg err:",e);if(btn){btn.disabled=false;btn.innerHTML="开始生图"}st("生图异常: "+e.message,"var(--warn)")}
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
function closeZoom(){document.getElementById("zoomLayer").classList.remove("show");document.getElementById("zoomDesc").textContent=""}
// 图库左右翻页
let ZOOM_LIST=[],ZOOM_IDX=0;
function zoomNav(dir){
 ZOOM_IDX=(ZOOM_IDX+dir+ZOOM_LIST.length)%ZOOM_LIST.length;
 const item=ZOOM_LIST[ZOOM_IDX];
 if(!item)return;
 document.getElementById("zoomImg").src=item.url;
 document.getElementById("zoomDesc").textContent=item.desc||"";
}
document.addEventListener("keydown",e=>{
 if(!document.getElementById("zoomLayer").classList.contains("show"))return;
 if(e.key=="ArrowLeft")zoomNav(-1);
 else if(e.key=="ArrowRight")zoomNav(1);
 else if(e.key=="Escape")closeZoom();
});
function reuseGallery(name){
 document.getElementById("subjInp").value=name.replace(/\.\w+$/,"");
 showTab("gen");
 st("已复用: "+name,"var(--accent2)");
}
async function genBatchPoem(bid){
 const btn=event.target;btn.disabled=true;btn.innerHTML='<span class="loading"></span>';
 try{
  const r=await api("/api/gen_batch_poem",{batch_id:bid});
  if(!r.ok){st("失败: "+(r.error||""),"var(--warn)");btn.disabled=false;btn.innerHTML='📝 故事';return}
  st("故事已更新","var(--accent2)");
  loadGallery();
 }catch(e){st("出错: "+e.message,"var(--warn)");btn.disabled=false;btn.innerHTML='📝 故事'}
}
function saveAll(){CARDS.forEach((c,i)=>{if(c.img)saveImg(i)})}

function showTab(t){
 document.getElementById("tabGen").className="tab"+(t=="gen"?" act":"");
 document.getElementById("tabLib").className="tab"+(t=="lib"?" act":"");
 document.getElementById("gwrap").style.display=t=="gen"?"block":"none";
 document.getElementById("gallery").className="gallery"+(t=="lib"?" show":"");
 if(t=="lib")loadGallery(document.getElementById('gSortBtn')?.dataset?.order||'');
}

async function loadGallery(order){
 order=order||document.getElementById('gSortBtn')?.dataset?.order||'newest';
 const g=document.getElementById("gallery");g.innerHTML="<span style='color:var(--hint)'>加载中...</span>";
 try{
  // 同时加载批次和图片
  const [br,ir]=await Promise.all([api("/api/list_batches"),api("/api/list_images")]);
  const batches=br.batches||[];
  const allImages=ir.images||[];
  if(!batches.length&&!allImages.length){g.innerHTML="<span style='color:var(--hint)'>暂无素材</span>";return}
  const sqVal=(document.getElementById("gSearch")?.value||"").trim().toLowerCase();
  let filtered=batches;
  if(sqVal) filtered=batches.filter(b=>{
   const txt=(b.subject||"")+" "+(b.poem||"")+" "+(b.style||"")+" "+((b.descriptions||[]).join(" "));
   return txt.toLowerCase().includes(sqVal)
  });
  if(order=="oldest") filtered=[...filtered].reverse();
  g.innerHTML=`<div class="g-toolbar">
   <input id="gSearch" placeholder="搜索主体、故事、描述词..." value="${sqVal}" onkeydown="if(event.key=='Enter')loadGallery(document.getElementById('gSortBtn').dataset.order||'')" />
   <button class="btng btng-d" id="gSortBtn" data-order="newest" style="font-size:10px;padding:3px 8px;white-space:nowrap" onclick="this.dataset.order=this.dataset.order=='newest'?'oldest':'newest';this.textContent=this.dataset.order=='newest'?'⏱ 最新':'⏱ 最早';loadGallery(this.dataset.order)">⏱ 最新</button>
   ${sqVal?`<button class="btng btng-s" style="font-size:10px;padding:3px 8px" onclick="document.getElementById('gSearch').value='';loadGallery()">✕ 清除</button>`:''}
   <span style="font-size:10px;color:var(--hint);margin-left:auto">${filtered.length}个批次</span>
  </div>`;
  // 先显示批次
  filtered.forEach(b=>{
   const imgs=b.images||[];
   const ds=b.descriptions||[];
   const n=b.subject||"未命名批次";
   // 批次卡片容器
   const bdiv=document.createElement("div");bdiv.className="g-batch";
   bdiv.innerHTML=`<div class="g-batch-hd">
    <span class="g-batch-subj">${b.poem||n}</span>
    <span class="g-batch-meta">${b.style||''} · ${imgs.length}/${ds.length}图</span>
    <button class="btng btng-d" style="font-size:9px;padding:2px 8px;flex-shrink:0" onclick="event.stopPropagation();genBatchPoem('${b.id}')">${b.poem?'🔄':'📝'}</button>
   </div>
   ${b.poem?`<div class="g-batch-poem">${b.poem}</div>`:''}
   <div class="g-batch-body show">
    ${imgs.length===0?'<span style="color:var(--hint);font-size:11px;padding:8px">等待生成...</span>':
     imgs.map((img,i)=>`<div class="g-batch-card" onclick="this.classList.toggle('folded')">
       <img src="/api/image/history/${img.file}" onclick="event.stopPropagation();const _items=${JSON.stringify(imgs.map((m,j)=>({url:'/api/image/history/'+m.file,desc:(m.prompt||ds[j]||'')})))};ZOOM_LIST=_items;ZOOM_IDX=${i};document.getElementById('zoomImg').src=this.src;document.getElementById('zoomDesc').textContent=_items[${i}].desc;document.getElementById('zoomLayer').classList.add('show')" />
       <div class="g-batch-info">
        <div class="g-batch-idx">#${i+1}</div>
        <div class="g-batch-desc">${(img.prompt||ds[i]||'').slice(0,80)}${((img.prompt||ds[i]||'').length>80?'...':'')}</div>
       </div>
      </div>`).join('')}
   </div>`;
   g.appendChild(bdiv);
  });
  // 旧版无批次图片也显示
  const batchedFiles=new Set();
  batches.forEach(b=>(b.images||[]).forEach(img=>batchedFiles.add(img.file)));
  const orphanImages=allImages.filter(img=>!batchedFiles.has(img.name));
  if(orphanImages.length>0){
   const od=document.createElement("div");od.className="g-batch";
   od.innerHTML=`<div class="g-batch-hd" onclick="this.nextElementSibling.classList.toggle('show')">
    <span class="g-batch-subj">📁 未归类素材</span>
    <span class="g-batch-meta">${orphanImages.length}张</span>
    <span class="g-batch-expand">▶</span>
   </div>
   <div class="g-batch-body show">
    ${orphanImages.map(img=>`<div class="g-batch-card">
      <img src="${img.url}" onclick="document.getElementById('zoomImg').src=this.src;document.getElementById('zoomLayer').classList.add('show')" />
      <div class="g-batch-info">
       <div class="g-batch-idx">${img.name}</div>
       <div class="g-batch-desc">${(img.prompt||'').slice(0,80)}</div>
      </div>
     </div>`).join('')}
   </div>`;
   g.appendChild(od);
  }
  // 更新数量
 }catch(e){g.innerHTML="<span style='color:var(--hint)'>加载失败: "+e.message+"</span>"}
 const gc=document.getElementById("galleryCount");
 try{
  const ir2=await api("/api/list_images");
  if(gc&&ir2.images)gc.textContent=ir2.images.length>0?`(${ir2.images.length})`:"";
 }catch(e){}
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
