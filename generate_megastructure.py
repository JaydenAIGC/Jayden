"""
巨构生成脚本 - APIMart gpt-image-2
异步任务: 提交 -> 轮询 -> 下载
"""

import os
import json
import requests
import time
from datetime import datetime

API_KEY = "sk-lrqeHfA8AtaELukCiTbmWrjBdI18umQPQaAFSEThcGDrsK84"
BASE_URL = "https://api.apimart.ai/v1"
MODEL = "gpt-image-2-official"
OUTPUT_DIR = "output"

os.makedirs(OUTPUT_DIR, exist_ok=True)

PROMPTS = [
    "一个巨大的空间网架结构横跨在空旷的灰色沙地平原上，由无数交错的钢制杆件和球形节点组成，像被放大了千万倍的工程结构。网架水平延伸，底部仅有几根纤细的支柱接触地面。杆件之间疏密有致，形成层层叠叠的透视。地面平坦，浅灰色沙地延伸到天际线。一个极小的人影站在其中一根支柱下。阴天均匀光，视野清晰，混凝土和钢材的本色。竖构图。",
    "四根巨大的混凝土巨柱从地面倾斜伸出，以不同角度在空中交汇，托起一个巨大的六边形平台。每根柱身有模板浇筑的横向纹理。平台底部是密肋梁格结构。四根柱子底部汇聚但留有缝隙。地面是平坦的深灰色碎石地。一个人影站在柱子之间仰头看顶部的平台。阴天均匀光，没有雾，清晰干燥。竖构图。",
    "一座巨大的双曲面混凝土塔，腰部收窄后向外张开，表面由密集的螺旋混凝土肋条环绕构成，像巨大的海螺壳。肋条之间形成深浅交错的阴影线条，从底部旋转到顶部开口。开口处露出内部的环形桁架。地面是干裂的浅灰色泥地。一个人影站在底部。阴天均匀光，视野通透。竖构图。",
    "一个巨大的悬挑结构：一根粗壮的混凝土核心筒从地面升起，顶部向一侧伸出一片巨大的水平桁架悬臂，悬臂长度超过核心筒高度，末端微微下垂。悬臂下缘是阶梯式收分，能看到钢结构连接节点。地面是平坦的灰色硬土。一个人影站在核心筒底部，视线沿悬臂延伸方向看去。阴天均匀光，清晰干燥。竖构图。",
    "一座张拉整体结构：一系列厚重的白色钢制压缩杆件由极细的高强度钢缆悬吊和拉紧，悬浮在半空中形成三维骨架网络。压缩杆粗壮，钢缆细到几乎看不见，整个结构像悬浮在空中的一座工程森林。地面是平坦的浅灰色干涸湖床。一个人影站在下方仰望那些悬浮的杆件。阴天均匀光，视野清晰。竖构图。",
]


def submit_task(prompt, index):
    """提交生图任务"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "n": 1,
        "size": "1024x1792",
        "response_format": "url"
    }
    resp = requests.post(f"{BASE_URL}/images/generations", headers=headers, json=payload, timeout=30)
    data = resp.json()
    task_id = data.get("data", [{}])[0].get("task_id")
    if task_id:
        print(f"  [提交] task_id: {task_id}")
        return task_id
    else:
        print(f"  [ERR] 提交失败: {json.dumps(data, ensure_ascii=False)[:200]}")
        return None


def poll_task(task_id):
    """轮询任务直到完成"""
    headers = {"Authorization": f"Bearer {API_KEY}"}
    url = f"{BASE_URL}/tasks/{task_id}?language=zh"

    for attempt in range(60):
        resp = requests.get(url, headers=headers, timeout=30)
        data = resp.json()
        status = data.get("data", {}).get("status", "unknown")
        progress = data.get("data", {}).get("progress", 0)
        print(f"    状态: {status} ({progress}%)", end="\r")

        if status == "completed":
            print(f"\n  [完成] 耗时: {data.get('data', {}).get('actual_time', '?')}秒")
            images = data.get("data", {}).get("result", {}).get("images", [])
            if images:
                url = images[0].get("url")
                if isinstance(url, list):
                    url = url[0]
                return url
            return None
        elif status in ("failed", "cancelled"):
            err = data.get("data", {}).get("error", "未知错误")
            print(f"\n  [失败] {err}")
            return None

        time.sleep(2)

    print("\n  [超时] 轮询超过120秒")
    return None


def download_image(img_url, index):
    """下载图片"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"megastructure_{timestamp}_{index + 1}.png"
    filepath = os.path.join(OUTPUT_DIR, filename)

    if img_url.startswith("http"):
        r = requests.get(img_url, timeout=60)
        with open(filepath, "wb") as f:
            f.write(r.content)
        print(f"  [OK] 已保存: {filepath}")
    else:
        print(f"  [ERR] 无效URL: {img_url[:80]}")
        return None
    return filepath


def main():
    print(f"模型: {MODEL}")
    print(f"数量: {len(PROMPTS)} 张")
    print(f"尺寸: 1024x1792 (9:16)")
    print("=" * 40)

    results = []
    for i, prompt in enumerate(PROMPTS):
        print(f"\n[{i+1}/{len(PROMPTS)}] 提交任务...")
        task_id = submit_task(prompt, i)
        if not task_id:
            results.append(None)
            continue

        img_url = poll_task(task_id)
        if img_url:
            path = download_image(img_url, i)
            results.append(path)
        else:
            results.append(None)

    print("\n" + "=" * 40)
    success = [r for r in results if r is not None]
    print(f"全部完成: {len(success)}/{len(PROMPTS)} 张成功")
    print(f"输出目录: {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
