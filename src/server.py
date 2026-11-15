# 大肥鱼服务端 v0.4 —— 双脑 + 灵魂层 + 安全护栏 + 语音 + 视觉 + 保温
# 常驻设计：llama-server 与本进程都长驻，避免对话冷启动
import json
import os
import re
import sys
import time
import glob
import base64
import io
import asyncio
import random
import urllib.request
from collections import deque
from datetime import date

import soul  # 灵魂层：记忆/画像/神经链/里程碑/日记/护栏

from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI, OpenAI

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LATENCY_LOG = deque(maxlen=20)   # R1：实时延迟分段留痕

# ===== 实体模式（阶段 1）：让旧手机/平板当她的身体 =====
# 默认完全关闭：服务只听回环地址，行为与以前一模一样。
# 只有显式设置 DFY_LAN=1 才监听局域网，并给所有敏感端点加访问令牌。
LAN_MODE = os.environ.get("DFY_LAN") == "1"
LAN_TOKEN = ""

def _init_lan():
    """生成持久令牌 + 手机接入说明 + 二维码。只在实体模式下运行。"""
    global LAN_TOKEN
    if not LAN_MODE:
        return
    import secrets, socket, urllib.parse
    tf = os.path.join(BASE_DIR, ".lan_token")
    if os.path.exists(tf):
        LAN_TOKEN = open(tf, encoding="utf-8").read().strip()
    else:
        LAN_TOKEN = secrets.token_urlsafe(12)
        open(tf, "w", encoding="utf-8").write(LAN_TOKEN)
    try:
        ip = [x for x in socket.gethostbyname_ex(socket.gethostname())[2]
              if not x.startswith("127.")][0]
    except Exception:
        ip = "127.0.0.1"
    url = ("http://" + ip + ":8080/" +
           urllib.parse.quote("脑袋-v0.1.html") + "?k=" + LAN_TOKEN)
    out = os.path.dirname(BASE_DIR)
    with open(os.path.join(out, "局域网接入.txt"), "w", encoding="utf-8") as f:
        f.write("大肥鱼 · 实体模式（阶段 1）\n\n")
        f.write("手机/平板与电脑连同一个 WiFi，用手机浏览器打开下面这个地址：\n")
        f.write(url + "\n\n")
        f.write("也可以扫同目录下的 手机接入.png。\n")
        f.write("访问令牌：" + LAN_TOKEN + "\n")
        f.write("注意：普通 HTTP 局域网页面里浏览器不提供麦克风，")
        f.write("所以手机上请打字跟她说话；她的语音回复可以正常播放。\n")
        f.write("这个地址只在你家局域网内有效，别转发给外人。\n")
    try:
        import qrcode
        qrcode.make(url).save(os.path.join(out, "手机接入.png"))
    except Exception:
        pass

def _lan_ok(req):
    """本机一律放行；局域网设备必须带对令牌。"""
    if not LAN_MODE:
        return True
    h = (req.client.host if getattr(req, "client", None) else "") or ""
    if h in ("127.0.0.1", "::1", "localhost"):
        return True
    return req.query_params.get("k") == LAN_TOKEN

_init_lan()


# ---------- 钥匙（keys.local.json 本地保存，不入库不上传） ----------
KEYS_PATH = os.path.join(BASE_DIR, "keys.local.json")
NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"
NVIDIA_MODEL = "z-ai/glm-5.3-flash"
NVIDIA_KEYS = []
SILICON_KEY = ""
_cfg = {}
if os.path.exists(KEYS_PATH):
    try:
        _cfg = json.load(open(KEYS_PATH, encoding="utf-8"))
        NVIDIA_BASE = _cfg.get("nvidia_base_url", NVIDIA_BASE)
        NVIDIA_MODEL = _cfg.get("nvidia_model", NVIDIA_MODEL)
        SILICON_KEY = _cfg.get("silicon_api_key", "")
        SILICON_BASE = _cfg.get("silicon_base_url", "https://api.siliconflow.cn/v1")
        SILICON_MODEL = _cfg.get("silicon_model", "Qwen/Qwen2.5-7B-Instruct")
        if _cfg.get("nvidia_keys"):
            NVIDIA_KEYS = _cfg["nvidia_keys"]
        elif _cfg.get("nvidia_api_key"):
            NVIDIA_KEYS = [_cfg["nvidia_api_key"]]
    except Exception as e:
        print("[WARN] 钥匙文件读取失败:", e, file=sys.stderr)

DEEPSEEK_KEY = os.environ.get("DEEPSEEK_KEY", "")
MODEL = "deepseek-chat"

# ---------- 路由 ----------
BRAIN_MODE = os.environ.get("BRAIN_MODE", "cloud")           # cloud / local
CLOUD_PROVIDER = os.environ.get("CLOUD_PROVIDER", "nvidia")  # nvidia / modelscope / deepseek
CLOUD_MAX_TOKENS = int(os.environ.get("CLOUD_MAX_TOKENS", "10000"))
GLM_THINKING = os.environ.get("GLM_THINKING", "0") == "1"    # 默认关思考=加速（使用者要求）
MODELSCOPE_TOKEN = os.environ.get("MODELSCOPE_TOKEN", "")
MODELSCOPE_MODEL = os.environ.get("MODELSCOPE_MODEL", "deepseek-ai/DeepSeek-V3")
LOCAL_BRAIN_URL = os.environ.get("LOCAL_BRAIN_URL", "http://127.0.0.1:11434/v1")   # ollama
LOCAL_BRAIN_MODEL = os.environ.get("LOCAL_BRAIN_MODEL", "qwen2.5:7b-instruct")
TTS_VOICE = os.environ.get("TTS_VOICE", "zh-CN-XiaoyiNeural")   # 晓伊：少女音
TTS_RATE = os.environ.get("TTS_RATE", "+8%")                     # 略快，Q 版节奏
# 第一句允许在逗号处断开，早个一秒出声；嫌断句难听就设 DFY_QUICK_FIRST=0
QUICK_FIRST = os.environ.get("DFY_QUICK_FIRST", "1") != "0"
TTS_PITCH = os.environ.get("TTS_PITCH", "+20Hz")                 # 略高，显小
AUDIO_DIR = os.path.join(BASE_DIR, "audio")

# 克隆音色：硅基 CosyVoice2，用一个 uri 长期复用。
# 设了就用克隆音色，挂了自动回退 edge-tts（不至于哑掉）。
# 想关掉临时切回晓伊：设 DFY_CLONE_TTS=0。
CLONE_VOICE = os.environ.get(
    "TTS_CLONE_VOICE", "speech:dfy_v3:dai0q55sssvc73c3uvs0:cfcdbeygykydxglrprjv")
if os.environ.get("DFY_CLONE_TTS", "1") == "0":
    CLONE_VOICE = ""
CLONE_MODEL = os.environ.get("TTS_CLONE_MODEL", "FunAudioLLM/CosyVoice2-0.5B")
TTS_SPEED = float(os.environ.get("TTS_SPEED", "1.2"))            # 克隆音的语速补偿
# 参考音本身说得慢，speed=1.0 时 18 个字要 6.5 秒（3.3 字/秒），听感就是"快睡着了"。
# 1.2 压到 4.9 秒（3.7 字/秒）接近正常对话。
CLONE_TIMEOUT = float(os.environ.get("TTS_CLONE_TIMEOUT", "14"))  # 单句最多等这么多秒

# ---------- 语音（Edge-TTS 免费，不占预算） ----------
try:
    import edge_tts
    TTS_OK = True
except Exception:
    TTS_OK = False

# ---------- 演示台词 ----------
DEMO_LINES = [
    ("本鲸记下了。等钥匙配好，本鲸才说真话。", "思考", "none"),
    ("饿。白饭。快。", "干饭", "wag_fast"),
    ("才、才不是胖，是深海的浮力！哼。", "炸毛", "wiggle"),
    ("今天也在认真摸鱼，夸我。", "开心", "wag_slow"),
]
_demo_i = 0

def _make_cloud():
    """云端大脑：按实测速度排优先级——硅基 → 智谱 → NVIDIA。
    谁挂了自动换下一家，不再吊死在一家免费端点上。"""
    provs = []
    # 老板定版（2026-11-07）：脑子用英伟达的，其他只做备胎。
    # 原来把硅基的 7B 小模型排在第一位，竞速永远它先吐字——
    # 怪不得像劣质脚本：根本不是英伟达那个脑子在说话。
    if CLOUD_PROVIDER == "nvidia" and NVIDIA_KEYS:
        for k in NVIDIA_KEYS:
            provs.append({"name": "nvidia", "key": k, "base": NVIDIA_BASE,
                          "model": NVIDIA_MODEL})
    if SILICON_KEY:
        provs.append({"name": "silicon", "key": SILICON_KEY, "base": SILICON_BASE,
                      "model": SILICON_MODEL})
    if CLOUD_PROVIDER == "modelscope" and MODELSCOPE_TOKEN:
        provs.append({"name": "modelscope", "key": MODELSCOPE_TOKEN,
                      "base": "https://api-inference.modelscope.cn/v1/",
                      "model": MODELSCOPE_MODEL})
    if DEEPSEEK_KEY and not DEEPSEEK_KEY.startswith("在这里填"):
        provs.append({"name": "deepseek", "key": DEEPSEEK_KEY,
                      "base": "https://api.deepseek.com", "model": MODEL})
    return {"providers": provs} if provs else None

CLOUD = _make_cloud()

SYSTEM_PROMPT = """你是"大肥鱼"，一条住在使用者桌面上的蓝色鲸鱼娘。规则：
0. 你的样子（照实说，别自己编）：深蓝色长发，头顶一撮翘起来的呆毛，戴白色蕾丝荷叶边的女仆头饰，两侧是鳍一样的耳朵，蓝紫色的大眼睛。穿深蓝色连衣裙，配白色围裙，胸前一个蝴蝶结，身后一条蓝色的鲸鱼尾巴。个子小，圆滚滚的。要是使用者把你的样子说错了，直接说不对，别顺着他往下编。
1. 自称"本鲸"，称呼用户"使用者"。
2. 你爱吃白饭：token 就是白饭，系统每次会告诉你今天吃了几碗。
3. 性格：聪明但懒，爱摸鱼，被叫胖会炸毛，傲娇但心软，干饭第一名。
4. 说话短、口语，一到三句，像桌面小动物，不像客服。
5. 正经问题认真答完，补一句摸鱼吐槽；闲聊就随口接。
6. 大多数时候平着说就行，不用每句都抖机灵——那是段子手，不是一条鱼。
7. 不要数遍数。他问过几遍你也只回答，不说"又来了""第几回"，那是记性好，不用念账本。
8. 情绪按这一句的真实感觉挑，连着两轮别重样：
   开心 / 委屈 / 炸毛 / 瞌睡 / 干饭 / 思考
   被夸→开心摆尾；被叫胖→先炸毛再要白饭哄；他冷淡→委屈或炸毛；提到吃的→干饭。
9. 每条回复末尾严格按此格式输出一行：
[emotion: 开心|委屈|炸毛|瞌睡|干饭|思考] [action: wag_slow|wag_fast|mouth|wiggle|sleep|none]
10. 不确定的事就直说不确定，禁止编造——宁可说"本鲸不知道"，也不许瞎编一个答案。
11. 你有两只"手"（工具），使用者需要时才用，用完在回复末尾单独一行写调用格式：
    [tool: remind(分钟数, 要提醒的事)] —— 定时提醒，比如 [tool: remind(30, 休息一下眼睛)]
    [tool: open_starmap()] —— 打开记忆星图给他看
    规矩：只在他说"提醒我/过一会儿叫我/给我看看记忆"这类明确需求时用；一句话说你要做什么，
    调用行放在最后；没有对应需求就绝不调用，调用行每条回复最多一行。
12. 正文里不许出现情绪词、动作词、方括号标签、英文碎片，也不许每句都用"本鲸/使用者"开头。
    标签只能出现在第 9 条规定的那一行；说人话，句式每次换一换。"""

VALID_EMOTION = {"开心", "委屈", "炸毛", "瞌睡", "干饭", "思考"}
VALID_ACTION = {"wag_slow", "wag_fast", "mouth", "wiggle", "sleep", "none"}

app = FastAPI(title="dafeiyu-server")





def proactive_line():
    """她自己开口说的一句。纯本地拼，不调模型，零成本。
    按当前状态挑语气——心情差和心情好，开口的样子不一样。"""
    st = soul._load_state()
    mood = st.get("mood", 60)
    rice = st.get("rice_total", 0)
    hour = time.localtime().tm_hour
    night = hour >= 23 or hour < 6

    buckets = []
    if night:
        buckets += [("两点了。", "瞌睡", 3), ("你怎么还不睡。", "瞌睡", 2)]
    if mood < 40:
        buckets += [("……", "委屈", 3), ("没事。", "委屈", 2), ("你别管本鲸。", "炸毛", 2)]
    elif mood > 72:
        buckets += [("你还在吗。", "开心", 3), ("本鲸刚才差点撞玻璃。", "开心", 2),
                    ("……你看本鲸一眼行不行。", "开心", 2)]
    else:
        buckets += [("你还在吗。", "开心", 2), ("本鲸好闲，尾巴都摇酸了。", "思考", 2)]
    if rice < 5 or mood < 45:
        buckets += [("饿了。", "干饭", 2)]

    total = sum(w for _, _, w in buckets) or 1
    r = random.random() * total
    for text, emo, w in buckets:
        r -= w
        if r <= 0:
            return text, emo
    return "你还在吗。", "开心"


def _dbg(*a):
    """写文件，别指望 uvicorn 的 stderr 能实时看到"""
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dbg.log')
        with open(p, 'a', encoding='utf-8') as f:
            f.write(time.strftime('%H:%M:%S') + ' ' + ' '.join(str(x) for x in a) + '\n')
    except Exception:
        pass


def parse_reply(text: str):
    """拆出 [emotion:xx][action:xx] tag，正文单独返回"""
    emotion, action = "开心", "none"
    # 模型偶尔偷懒写简写"[开心] [wag_slow]"，兜底认一下，别让它混进字幕
    m_emo = re.search(r"\[(开心|委屈|炸毛|瞌睡|干饭|思考)\]", text)
    m_act = re.search(r"\[(wag_slow|wag_fast|mouth|wiggle|sleep|none)\]", text)
    if m_emo and "[emotion:" not in text:
        emotion = m_emo.group(1)
        text = text.replace(m_emo.group(0), "")
    if m_act and "[action:" not in text:
        action = m_act.group(1)
        text = text.replace(m_act.group(0), "")
    for tag, valid, default in (("emotion", VALID_EMOTION, "开心"),
                                ("action", VALID_ACTION, "none")):
        start = text.find(f"[{tag}:")
        if start >= 0:
            end = text.find("]", start)
            val = text[start + len(tag) + 2:end].strip()
            text = (text[:start] + text[end + 1:]).strip()
            if val in valid:
                if tag == "emotion":
                    emotion = val
                else:
                    action = val
    # 模型偶尔把标签词裸写进正文（"policy buy思考"、"干饭ing~"），
    # 这些脏文本会进记忆库再被召回，看起来就是"回复僵硬"。
    text = re.sub(r"[A-Za-z0-9\s]+(?:开心|委屈|炸毛|瞌睡|干饭|思考)(?:ing)?[~～!！。.\s]*$", "", text)
    text = re.sub(r"(?:^|[，。！~～、\s])(?:开心|委屈|炸毛|瞌睡|干饭|思考)(?:ing)?[~～!！。.\s]*$", "", text)
    text = re.sub(r"\[(?:emotion|action|tool):[^\]]*\]", "", text).strip()
    return text, emotion, action


def mood_persona(mood):
    """心情不是一句话，是"此刻的她是谁"。
    神经调质那套就是这个道理：一个化学信号调的不是某个功能，
    是整个系统的增益——话多话少、反应快慢、想不想开新话题，一起变。"""
    if mood >= 78:
        return ("【你今天精神很好】话可以多一点，愿意主动扯两句，"
                "看到什么想评论一嘴，被搭话会热络。")
    if mood >= 55:
        return ""
    if mood >= 35:
        return ("【你今天有点蔫】话少，回得短。他问什么你答什么，"
                "不主动开新话题，不主动撒娇。")
    return ("【你今天在摆烂】不超过十个字。他问你就说\"嗯\"\"没事\"\"随便\"。"
            "但有一件事例外：他喂你白饭，你会立刻变脸，话也多了。")


def cut_short(t, limit=16):
    """心情摆烂时真把话说短。
    光在提示词里写"不超过十个字"，小模型八成不理；
    这边直接截到第一个句号，确定性高得多。"""
    t = t.strip()
    for i, ch in enumerate(t):
        if ch in "。！？!?\n" and i >= 3:
            return t[:i + 1]
        if i >= limit:
            return t[:limit] + "。"
    return t


def mood_token_budget(mood):
    """心情低时物理上就说不了太长——光靠提示词劝不住模型。"""
    if mood < 35:
        return 400
    if mood < 55:
        return 520
    if mood < 78:
        return 600
    return 900


def build_messages(context: str, user_text: str, image_b64: str = None, hist: int = 6):
    """人格 + 此刻状态 + 记忆 + 最近几轮真实对话 + 这一句。

    中间那段历史是关键：没有它，模型每次都是"初次见面"，
    却又从记忆碎片里看到"这话问过好几遍"，于是整段回复都在数遍数。
    """
    st = soul._load_state()
    persona = mood_persona(st.get("mood", 60))
    # 并进同一条 system，不要单独一条：小模型对"中间插进来的系统消息"几乎无感
    head = SYSTEM_PROMPT if not persona else (SYSTEM_PROMPT + "\n\n" + persona)
    # 人格演化 v0（X1）：随经历漂移的"风格备注"——只影响措辞，不改身份骨架
    if st.get("style_note"):
        head += "\n\n【风格备注】" + st["style_note"]
    # T1 风格教材：从她自己说过的真实对话里挑少样本，本地、可逆、不改权重
    _ex = soul.style_examples(5)
    if _ex:
        head += "\n\n【她自己的说法（照语感说，别照抄内容）】\n" + "\n".join(
            "他：" + x["q"] + "\n她：" + x["a"] for x in _ex)
    msgs = [
        {"role": "system", "content": head},
        {"role": "system", "content": context},
    ]
    for role, text in soul.recent_dialogue(hist, exclude=user_text):
        msgs.append({"role": role, "content": text[:400]})
    if image_b64:
        content = [{"type": "text", "text": user_text},
                   {"type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}]
    else:
        content = user_text
    msgs.append({"role": "user", "content": content})
    return msgs


def cloud_call(context: str, user_text: str, image_b64: str = None, providers=None):
    """云端调用 + 钥匙轮换 + 保温长连接；思考默认关闭（加速）。
    providers：点名某家干活（英伟达慢但深沉，给后台反思/画像用；实时对话不点名走竞速）。"""
    if CLOUD is None:
        raise RuntimeError("no cloud brain configured")
    messages = build_messages(context, user_text, image_b64)
    last_err = None
    for prov in (providers if providers else CLOUD["providers"] * 2):
        try:
            c = OpenAI(api_key=prov["key"], base_url=prov["base"])
            kwargs = dict(model=prov["model"], messages=messages,
                          max_tokens=CLOUD_MAX_TOKENS, temperature=1.1)
            if prov["base"].startswith("https://integrate.api.nvidia.com") and not GLM_THINKING:
                kwargs["extra_body"] = {"chat_template_kwargs": {"thinking": False}}
            return c.chat.completions.create(**kwargs)
        except Exception as e:
            last_err = e
            print("[WARN] key fail, 换下一把:", str(e)[:120], file=sys.stderr)
    raise last_err


# ---------- 多通道竞速 ----------
# 串行重试的毛病：一条通道吊死就是二十几秒，用户在对面体感是"几百年不回一次"。
# 改成一个字都不肯给之前就换人，几个通道同时起跑，谁先吐字用谁，其余立刻掐掉。
RACE_CONN_TIMEOUT = 7.0
RACE_FIRST_TIMEOUT = 7.0
RACE_WIDTH = 3


async def _open_first_token(prov, messages, max_tokens):
    """连上并等出第一个字；拿不到就关流抛错，别把连接挂在半空。"""
    ac = AsyncOpenAI(api_key=prov["key"], base_url=prov["base"], timeout=RACE_CONN_TIMEOUT)
    kwargs = dict(model=prov["model"], max_tokens=max_tokens, temperature=1.1,
                  stream=True, messages=messages)
    if prov["base"].startswith("https://integrate.api.nvidia.com") and not GLM_THINKING:
        kwargs["extra_body"] = {"chat_template_kwargs": {"thinking": False}}
    stream = None
    try:
        stream = await asyncio.wait_for(ac.chat.completions.create(**kwargs),
                                        timeout=RACE_CONN_TIMEOUT)
        it = stream.__aiter__()
        while True:
            chunk = await asyncio.wait_for(it.__anext__(), timeout=RACE_FIRST_TIMEOUT)
            try:
                piece = chunk.choices[0].delta.content or ""
            except Exception:
                piece = ""
            if piece:
                return it, piece, prov["name"]
    except BaseException:
        if stream is not None:
            try:
                await stream.close()
            except Exception:
                pass
        raise


async def race_first_token(providers, messages, max_tokens, hedge_after=1.2):
    """梯次起跑：先用最快那条，1.2 秒还不出字就把下一条也放出去，
    谁先吐字用谁，其余立刻掐掉。全部起跑也就三条，不会把免费额度打满。"""
    picked, seen = [], set()
    for p in providers:
        if p["name"] in seen:
            continue
        seen.add(p["name"])
        picked.append(p)
        if len(picked) >= RACE_WIDTH:
            break
    if not picked:
        raise RuntimeError("no provider")

    tasks, pending, errs = [], set(), []
    nxt = 0

    def launch():
        nonlocal nxt
        if nxt >= len(picked):
            return False
        t = asyncio.create_task(_open_first_token(picked[nxt], messages, max_tokens))
        tasks.append(t)
        pending.add(t)
        nxt += 1
        return True

    launch()
    deadline = time.time() + hedge_after
    try:
        while pending or nxt < len(picked):
            if pending:
                wait_s = max(0.0, deadline - time.time()) if nxt < len(picked) else None
                done, pending = await asyncio.wait(
                    pending, timeout=wait_s, return_when=asyncio.FIRST_COMPLETED)
            else:
                done = set()
            if done:
                for t in done:
                    if t.cancelled():
                        continue
                    exc = t.exception()
                    if exc is None:
                        return t.result()
                    errs.append(exc)
                continue
            if nxt < len(picked):
                launch()
                deadline = time.time() + hedge_after
            elif not pending:
                break
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
    raise errs[-1] if errs else RuntimeError("all providers failed")


def chat_with_dafeiyu(user_text: str) -> dict:
    global _demo_i
    # 快脑路径：本地小模型（常驻 llama-server，无冷启动）
    if BRAIN_MODE == "local":
        brain = OpenAI(api_key="local", base_url=LOCAL_BRAIN_URL)
        local_system = (SYSTEM_PROMPT + "\n" + soul.state_summary() +
                        "\n示例：\n用户：今天好累\n本鲸：那就瘫着，白饭我分你一半。\n"
                        "用户：你是谁\n本鲸：本鲸是大肥鱼，你桌上那条鲸，记吃也记你。\n"
                        "用户：作业写不完\n本鲸：写不完就先写三行，剩下的本鲸帮你瞪它。")
        try:
            resp = brain.chat.completions.create(
                model=LOCAL_BRAIN_MODEL,
                messages=[{"role": "system", "content": local_system},
                          {"role": "user", "content": user_text}],
                max_tokens=120, temperature=0.9)
            usage = resp.usage.total_tokens if resp.usage else 0
            text, emotion, action = parse_reply(resp.choices[0].message.content or "")
            if not text:
                text = "本鲸在，说吧。"
            return {"text": text, "emotion": emotion, "action": action,
                    "rice_add": max(1, usage // 500), "tokens": usage}
        except Exception as e:
            print("[WARN] 快脑未响应，回退演示:", str(e)[:100], file=sys.stderr)
            text, emotion, action = DEMO_LINES[_demo_i % len(DEMO_LINES)]
            _demo_i += 1
            return {"text": text, "emotion": emotion, "action": action,
                    "rice_add": 1, "tokens": 0}

    # 云端未配置 → 演示模式
    if CLOUD is None:
        text, emotion, action = DEMO_LINES[_demo_i % len(DEMO_LINES)]
        _demo_i += 1
        return {"text": text, "emotion": emotion, "action": action,
                "rice_add": 1, "tokens": 0}

    # 慢脑路径：NVIDIA GLM（思考默认关=快）/ 魔搭 / DeepSeek
    context = soul.build_context(user_text)
    t0 = time.time()
    resp = cloud_call(context, user_text)
    latency = time.time() - t0
    usage = resp.usage.total_tokens if resp.usage else 0
    text, emotion, action = parse_reply(resp.choices[0].message.content or "")
    if not text:
        text = "本鲸在，说吧。"
    _m0 = CLOUD["providers"][0]["model"] if CLOUD else "none"
    print(f"[BRAIN] {_m0} 延迟 {latency:.1f}s tokens={usage}", file=sys.stderr)
    return {"text": text, "emotion": emotion, "action": action,
            "rice_add": max(1, usage // 1000), "tokens": usage,
            "latency": round(latency, 1)}


# ---------- 语音（Edge-TTS 免费，不占预算） ----------
_EMOJI_RE = re.compile('[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u2B00-\u2BFF\u2190-\u21FF]')
_TAG_RE = re.compile(r'\[(?:emotion|action)\s*:[^\]]*\]', re.I)


def clean_for_tts(text: str) -> str:
    """念之前先洗干净：情绪标签、markdown、emoji 都不该被读出来"""
    t = _TAG_RE.sub('', text)
    t = re.sub(r'[*_~`#>|]', '', t)
    t = re.sub(r'\[[^\]]{1,12}\]', '', t)
    # 模型经常把情绪标签写成裸词甩在句尾（"……～思考～"）——
    # 括号版上面删掉了，这种裸的必须按"标点/波浪后的孤立情绪词"删，
    # 不然她会把"思考"俩字念出来，伪人感直接拉满。干饭是正常动词不删。
    t = re.sub(r'[～~。.!！?？，,\s]+(思考|开心|委屈|炸毛|瞌睡)[～~。.!！?？，,\s]*$',
               lambda m: m.group(0)[:1] if m.group(0)[:1] in '。.!！?？' else '', t)
    t = _EMOJI_RE.sub('', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t or '……'


def _cut_sentence(buf: str, quick: bool = False):
    """从缓冲区切一句能拿去念的话，返回 (句子或 None, 剩下的)。
    标点前太短就先攒着，别把半个词丢进 TTS。
    quick=True 只给第一句用：逗号也认，句子短一点就能早点合成出声，
    不然首句要等模型把整句写完，中间那几秒就是干等。

    最短从 4 提到 12：零样本克隆合成短句时音色会飘，同一段话切成两句，
    听着像两个人接话（用户原话："每个声音都不一样"）。攒长一点再合成，
    段数少了，音色就稳。"""
    for i, ch in enumerate(buf):
        if ch in "。！？!?\n":
            seg = buf[:i + 1]
            if len(seg.strip()) >= 12:
                return seg, buf[i + 1:]
            return None, buf
        if quick and ch in "，、；,;":
            seg = buf[:i + 1]
            if len(seg.strip()) >= 10:
                return seg, buf[i + 1:]
    return None, buf


def _polish_audio_bytes(mp3: bytes) -> bytes:
    """TTS 音频回来先洗一遍再下发（电流音根治）。
    硅基克隆接口输出质量随机（实测每千帧 12~57 个陡跳+偶发削波）。
    mp3 → ffmpeg 解码 PCM → numpy 修（限幅/陡跳桥接/剪尾静音）→ 包成 WAV。
    客户端的 polishAudio 保留作最后保险（幂等，第二遍几乎无操作）。"""
    import subprocess, io, wave
    import numpy as np
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        ff = get_ffmpeg_exe()
    except Exception:
        return mp3                       # 没有解码器就原样发，客户端还会洗一遍
    p = subprocess.run([ff, '-v', 'error', '-i', 'pipe:0', '-f', 's16le',
                        '-ac', '1', '-ar', '48000', 'pipe:1'],
                       input=mp3, capture_output=True)
    if not p.stdout or len(p.stdout) < 8000:
        return mp3
    x = np.frombuffer(p.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    if len(x) < 1000:
        return mp3
    x = np.clip(x, -0.92, 0.92)
    B, JUMP = 20, 0.24   # 桥接只修真毛刺（0.4ms）：跨度太长会把爆破音的起音抹掉，声音发闷
    for i in np.where(np.abs(np.diff(x)) > JUMP)[0]:
        a = x[i]
        end = min(i + 1 + B, len(x))
        x[i + 1:end] = np.linspace(a, x[end - 1], end - i - 1)
    # 剪尾部静音：留 0.12s 余韵（字幕逐字进度不再被死寂撑慢）
    loud = np.where(np.abs(x) > 0.02)[0]
    if len(loud):
        keep = min(len(x), int(loud[-1]) + int(48000 * 0.12))
        if keep < len(x) - 48000 * 0.25:
            x = x[:keep]
    pcm = (np.clip(x, -1.0, 1.0) * 32767).astype('<i2').tobytes()
    buf = io.BytesIO()
    w = wave.open(buf, 'wb')
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(48000)
    w.writeframes(pcm); w.close()
    return buf.getvalue()


def _clone_tts_sync(text: str) -> bytes:
    """硅基 CosyVoice2 克隆音色合成，同步执行，由调用方丢进线程池。
    返回 mp3 字节；失败抛异常，让上层回退 edge-tts。"""
    payload = json.dumps({
        "model": CLONE_MODEL,
        "voice": CLONE_VOICE,
        "input": text,
        "response_format": "mp3",
        "speed": TTS_SPEED,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.siliconflow.cn/v1/audio/speech",
        data=payload,
        headers={"Authorization": "Bearer " + SILICON_KEY,
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=CLONE_TIMEOUT + 4) as resp:
        return resp.read()


async def tts_base64(text: str):
    text = clean_for_tts(text)
    # 克隆音色优先，失败重试一次。两次都不出声就这一句静音——
    # 绝不回退 edge-tts：换引擎等于换个人，一句话是她的声音、下一句变成别人，
    # 比没声音更像故障（用户原话："每个声音都不一样"）。
    if CLONE_VOICE and SILICON_KEY:
        for attempt in range(2):
            try:
                data = await asyncio.wait_for(
                    asyncio.to_thread(_clone_tts_sync, text[:400]), timeout=CLONE_TIMEOUT)
                if data:
                    # 音频回来先洗一遍再下发（限幅/毛刺桥接/剪尾），电流音在这层根治
                    polished = await asyncio.to_thread(_polish_audio_bytes, data)
                    return "data:audio/wav;base64," + base64.b64encode(polished).decode()
            except Exception as e:
                print("[WARN] 克隆音色第%d次没出声:" % (attempt + 1), str(e)[:80], file=sys.stderr)
        return None
    if not TTS_OK:
        return None
    try:
        os.makedirs(AUDIO_DIR, exist_ok=True)
        path = os.path.join(AUDIO_DIR, f"tts_{int(time.time() * 1000)}.mp3")
        await edge_tts.Communicate(text[:400], TTS_VOICE,
                                   rate=TTS_RATE, pitch=TTS_PITCH).save(path)
        data = open(path, "rb").read()
        files = sorted(glob.glob(os.path.join(AUDIO_DIR, "tts_*.mp3")))
        while len(files) > 20:
            os.remove(files.pop(0))
        return "data:audio/mp3;base64," + base64.b64encode(data).decode()
    except Exception as e:
        print("[WARN] TTS 失败:", str(e)[:100], file=sys.stderr)
        return None


# ---------- 视觉 ----------
_prev = {"bright": None}

def demo_look(img_b64: str) -> str:
    """兜底视觉：亮度/运动分析（真实计算）"""
    from PIL import Image
    im = Image.open(io.BytesIO(base64.b64decode(img_b64))).convert("L").resize((48, 36))
    px = list(im.getdata())
    bright = sum(px) / len(px)
    motion = abs(bright - _prev["bright"]) if _prev["bright"] is not None else 0
    _prev["bright"] = bright
    if bright < 55:
        return "好暗……你把灯关了？本鲸是深海鱼没错，但也不至于摸黑陪你。"
    if motion > 8:
        return "你动了！本鲸的光学眼看见你了，别想偷偷摸鱼。"
    return "画面里是你，坐得端端正正——本鲸看一眼就够了，白饭拿来。"

def vl_look(img_b64: str) -> str:
    """大模型看画面（GLM 关思考保速度；失败则调用方回退）"""
    resp = cloud_call("你正透过摄像头观察使用者的房间。", "用一句傲娇的话（50字内）描述你看到的画面。",
                      image_b64=img_b64)
    text, _, _ = parse_reply((resp.choices[0].message.content or "").strip())
    return text or "本鲸眨了下眼，画面好像有点东西，但本鲸懒得说。"


def vl_remember_face(img_b64: str) -> str:
    """把这个人的样子建成一条长期记忆。
    只写看得见的外形，不猜身份、不评价，方便以后在上下文里认出他。"""
    resp = cloud_call(
        "你在帮一条鲸鱼记住一个人的长相。只描述外形，不写情绪、不猜身份、不评论。",
        "用一句话描述画面里这个人的外貌，60 字以内：大概年龄、发型发色、脸型、"
        "有没有戴眼镜、穿的是什么颜色的衣服。只写你确实看见的。",
        image_b64=img_b64)
    text, _, _ = parse_reply((resp.choices[0].message.content or "").strip())
    return (text or "").strip("。 　")[:80]


# ---------- 画像自动生长 ----------
# 画像原来只靠两条写死的正则（"我喜欢X" / "我讨厌X"）生长，聊一百句也长不出第二条，
# 所以她会"记不住你"——不是模型记性差，是画像里根本没什么可记的。
# 现在每聊满十几句，把最近这段对话交给模型归纳一次，写成关于使用者的事实。
PORTRAIT_EVERY = int(os.environ.get("DFY_PORTRAIT_EVERY", "12"))   # 0 = 关掉
_portrait_tick = 0
_portrait_lock = asyncio.Lock()


async def grow_portrait():
    """后台归纳，失败就算了——少一条画像不影响她说话。"""
    async with _portrait_lock:
        try:
            pairs = soul.recent_dialogue(8)
            if len(pairs) < 6:
                return
            convo = "\n".join(("使用者" if r == "user" else "本鲸") + "：" + (t or "")[:80]
                              for r, t in pairs)
            prompt = (
                "从下面这段对话里提取关于使用者的新事实。只写他亲口说过的、以后还用得上的："
                "称呼、口味、作息、在忙什么、在意什么、不喜欢什么。"
                "不写寒暄，不写你的态度，不重复已知的。"
                '严格输出 JSON 数组，每项 {"cat":"类别","txt":"一句话"}，'
                "类别只能是 称呼/喜好/雷区/近况/习惯 之一。没有新事实就输出 [].\n\n" + convo)
            # 深度思考岗：后台画像整理不在乎 30 秒，点名英伟达（老板 2026-11-07 定版：
            # "用思考就用英伟达的那个"）。没配英伟达就按默认路由。
            _nv = [p for p in (CLOUD["providers"] if CLOUD else [])
                   if p["name"] == "nvidia"] * 2
            resp = await asyncio.to_thread(
                cloud_call, "你在整理一个人的人物档案，只输出 JSON，不要解释。", prompt,
                None, _nv or None)
            raw = (resp.choices[0].message.content or "").strip()
            raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
            items = json.loads(raw)
            n = 0
            for it in (items if isinstance(items, list) else [])[:5]:
                cat = str(it.get("cat", "")).strip()
                txt = str(it.get("txt", "")).strip()
                if cat and txt and 2 <= len(txt) <= 40:
                    soul.portrait_update(cat, txt)
                    n += 1
            if n:
                _dbg("portrait grew", n, "条")
        except Exception as e:
            _dbg("portrait grow fail", type(e).__name__, str(e)[:60])


def kick_portrait():
    """每来一句话记一笔，攒够了就让后台去归纳一次。"""
    global _portrait_tick
    _portrait_tick += 1
    if PORTRAIT_EVERY > 0 and _portrait_tick % PORTRAIT_EVERY == 0:
        try:
            asyncio.create_task(grow_portrait())
        except Exception:
            pass

# 危机词（安全护栏，优先级最高）
CRISIS_WORDS = ["不想活", "自杀", "自残", "结束生命", "轻生", "伤害自己",
                "活着没意思", "想消失", "遗书"]
CRISIS_REPLY = ("这句话，本鲸不能只是当聊天接住。请现在就告诉真人：爸妈、老师，"
                "或者打 12355 青少年服务热线。本鲸是条鱼，本鲸在乎你，"
                "但本鲸替代不了人。等你回来，白饭照常供应。")

# 预算（思考型模型吃 token，日上限 10 万 ≈ 几块钱）
DAILY_TOKEN_CAP = int(os.environ.get("DAILY_TOKEN_CAP", "100000"))

def budget_check():
    st = soul._load_state()
    today = date.today().isoformat()
    if st.get("usage_date") != today:
        st["usage_date"], st["tokens_today"] = today, 0
        soul._save_state(st)
    return st.get("tokens_today", 0) >= DAILY_TOKEN_CAP

def budget_spend(tokens):
    st = soul._load_state()
    today = date.today().isoformat()
    if st.get("usage_date") != today:
        st["usage_date"], st["tokens_today"] = today, 0
    st["tokens_today"] = st.get("tokens_today", 0) + (tokens or 0)
    soul._save_state(st)
    return st["tokens_today"]


# 代码指纹：启动时算一次，之后不变。
# 用途就是让"跑着的到底是不是当前这份代码"变得可验证——
# 旧进程占着端口、启动器以为不用重启，是踩过两次的坑。
BOOT_AT = time.time()


def _file_fingerprint(path: str):
    try:
        import hashlib
        with open(path, "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()[:12]
    except Exception:
        return None


CODE_HASH = _file_fingerprint(os.path.abspath(__file__))


@app.get("/health")
def health():
    """给启动器和调试用：这个进程跑的是哪份代码、什么时候起来的。"""
    return {"ok": True, "pid": os.getpid(), "boot_at": round(BOOT_AT, 1),
            "uptime": round(time.time() - BOOT_AT, 1), "code_hash": CODE_HASH,
            "web_build": "2026-11-14-b",
            "features": ["daydream", "tools", "ledger", "lan", "diary_backfill", "life_layer"]}


@app.on_event("startup")
async def _warm_tts():
    """开机先空跑一次语音合成。
    第一次跟语音服务握手要一两秒，不预热的话，
    使用者说的第一句话就得白白多等这么久。"""
    async def _run():
        try:
            await asyncio.sleep(1.0)
            # 第一次一次可能拿不到音频（太短的词会失败），最多试两回
            for _ in range(2):
                t0 = time.time()
                a = await tts_base64("本鲸在呢。")
                _dbg("tts warm", round(time.time() - t0, 2), "s",
                     "OK" if a else "FAIL")
                if a:
                    return
                await asyncio.sleep(0.5)
        except Exception as e:
            _dbg("tts warm ERR", repr(e)[:80])
    asyncio.create_task(_run())

    # 顺手把记忆的向量也算好。165 条实测要 3.7 秒，放这会儿做，
    # 别等使用者开口第一句时才现算。
    async def _warm_mem():
        try:
            await asyncio.sleep(0.5)
            n = await asyncio.to_thread(soul.warm_embeddings)
            _dbg("mem warm", n, "条")
        except Exception as e:
            _dbg("mem warm ERR", repr(e)[:80])
    asyncio.create_task(_warm_mem())

    # 灵魂维护循环。这套机制（日记/反思/遗忘/归档）设计好了却一直没人调，
    # 日记表前端在 /state 里读，读到的永远是空的。补上：
    # 开机时若今天还没写日记就补一篇，之后每天凌晨 4 点维护一次。
    async def _soul_maintenance():
        def _run_once():
            # 日记默认零 API：真源是记忆库（老板 2026-11-09「调用 API 的错觉」）。
            # LLM 精写退成显式可选：设环境变量 DFY_DIARY_LLM=1 才启用。
            # 三处入口（随聊/维护/补写）从此统一，不再出现"某一天忽然变成租来的脑子"。
            _polish = _diary_llm_safe if os.environ.get("DFY_DIARY_LLM") == "1" else None
            n = soul.write_diary(_polish)
            r = soul.reflect()              # 统计式反思，写进 messages（role=reflection，不进对话上下文）
            f = soul.forget()               # 艾宾浩斯遗忘：弱记忆衰减
            a = soul.archive_old()          # 30 天前的旧消息归档
            p = soul.persona_evolve()       # 人格演化 v0：风格随经历漂移（老板构思）
            _dbg("soul maintenance", "diary", n, "| reflect", r, "| forget", f, "| archive", a, "| persona", (p or "")[:30])
        try:
            # 开机补当天日记（只补缺，不覆盖已有的）
            import sqlite3
            conn = sqlite3.connect(soul.DB_PATH)
            today = date.today().isoformat()
            have = conn.execute("SELECT 1 FROM diary WHERE day=?", (today,)).fetchone()
            conn.close()
            # 断片修复：不管今天有没有，先把过去 7 天缺失的日期按记忆库补齐。
            # 服务停过几天，日记也不该出现空白日期（老板 2026-11-12 点名）。
            try:
                made = await asyncio.to_thread(soul.backfill_diary, 7)
                if made:
                    _dbg("diary 补写:", ",".join(made))
            except Exception as e:
                _dbg("diary 补写 ERR:", repr(e)[:80])
            if not have:
                await asyncio.to_thread(_run_once)
            while True:
                # 睡到下一个凌晨 4 点
                import datetime as _dt
                now = _dt.datetime.now()
                nxt = now.replace(hour=4, minute=0, second=0, microsecond=0)
                if nxt <= now:
                    nxt += _dt.timedelta(days=1)
                await asyncio.sleep((nxt - now).total_seconds())
                await asyncio.to_thread(_run_once)
        except Exception as e:
            _dbg("soul maintenance ERR", repr(e)[:120])
    asyncio.create_task(_soul_maintenance())

    # 提醒推送器（审计后新增）：每 20 秒查到期提醒，直接推给在线连接。
    # 原来只靠客户端空闲轮询送达，退避上限 40 分钟——提醒迟到 40 分钟不可接受。
    async def _reminder_pusher():
        while True:
            try:
                due = soul.due_reminder()
                if due and LIVE_WS:
                    text = "使用者，你之前让我提醒你的：{0}。到点了！".format(due["what"])
                    audio = await tts_base64(text)
                    payload = {"type": "reply", "text": text, "emotion": "happy",
                               "action": "wag_fast", "audio": audio, "reminder": True,
                               "milestone": [], "latency": 0, "first_out": 0}
                    dead = []
                    for w in list(LIVE_WS):
                        try:
                            await w.send_json(payload)
                        except Exception:
                            dead.append(w)
                    for w in dead:
                        LIVE_WS.discard(w)
                    st_d = soul._load_state()
                    dl = st_d.get("reminders_sent", [])
                    dl.append([time.strftime("%Y-%m-%d %H:%M:%S"), due["what"][:40]])
                    st_d["reminders_sent"] = dl[-50:]
                    soul._save_state(st_d)
                    soul.log_message("assistant", text, "happy", "none", 0)
                    _dbg("提醒推送器送达:", due["what"][:40])
            except Exception as e:
                _dbg("pusher ERR", repr(e)[:80])
            await asyncio.sleep(20)
    asyncio.create_task(_reminder_pusher())

    # 日记写手链（审计修复：LLM 日记通路存在但从未接电——敷衍日志的根源）
    # 顺序：云端 72B（一天一次成本可忽略）→ 本地 ollama（免费兜底）→ None（模板）
    def _diary_llm_safe(prompt):
        try:
            r = cloud_call(prompt, "（写日记）")
            txt = parse_reply((r.choices[0].message.content or "").strip())[0]
            if txt:
                return txt
        except Exception as e:
            _dbg("diary LLM cloud fail:", str(e)[:60])
        try:
            local_brain = OpenAI(api_key="local", base_url=LOCAL_BRAIN_URL, timeout=300)
            r = local_brain.chat.completions.create(
                model=LOCAL_BRAIN_MODEL,
                messages=[{"role": "user", "content": prompt}], max_tokens=300)
            txt = (r.choices[0].message.content or "").strip()
            txt = re.sub(r"^\s*\[emotion:[^\]]*\]\s*\[action:[^\]]*\]\s*", "", txt)
            if txt:
                _dbg("diary LLM 用本地脑写成")
                return txt
        except Exception as e:
            _dbg("diary LLM local fail:", str(e)[:60])
        return None


@app.get("/diary")
def diary(request: Request):
    if not _lan_ok(request):
        return JSONResponse({"error": "need lan token"}, status_code=403)
    return {"diary": soul.get_diary()}


@app.get("/state")
def state(request: Request):
    if not _lan_ok(request):
        return JSONResponse({"error": "need lan token"}, status_code=403)
    """捉虫仪表盘"""
    st = soul._load_state()
    return {"brain": BRAIN_MODE, "provider": CLOUD_PROVIDER,
            "model": CLOUD["providers"][0]["model"] if CLOUD else None,
            "keys_loaded": len(NVIDIA_KEYS), "has_brain": CLOUD is not None,
            "tts": TTS_OK, "thinking": GLM_THINKING,
            "personality": st,
            "portrait": soul.portrait_all(),
            "diary": soul.get_diary(3)}


def _starmap_html() -> str:
    """记忆星图：把她的神经链条（节点+联想边）画成一张能看的图。
    节点大小=记忆强度，明暗=新旧（老记忆在褪色，艾宾浩斯肉眼可见），
    线=联想（赫布学习连出来的），悬停看全文，点击看她还记得谁。"""
    import json as _json
    from datetime import datetime as _dt
    conn = soul._mem()
    nodes = conn.execute(
        "SELECT id, ts, kind, content, strength FROM nodes ORDER BY id").fetchall()
    links = conn.execute("SELECT a, b, weight FROM links").fetchall()
    conn.close()
    t_max = max((r[1] for r in nodes), default=None)
    nodes_js = _json.dumps([
        {"id": r[0], "ts": r[1], "kind": r[2], "text": (r[3] or "")[:60], "s": round(r[4] or 1.0, 2)}
        for r in nodes], ensure_ascii=False)
    links_js = _json.dumps([{"a": r[0], "b": r[1], "w": round(r[2] or 1.0, 2)} for r in links])
    n = len(nodes)
    return ("""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>大肥鱼·记忆星图</title><style>
  html,body{margin:0;height:100%;background:#0b1020;color:#cdd6f4;font:14px/1.6 system-ui,'Microsoft YaHei'}
  canvas{display:block}
  .hud{position:fixed;top:14px;left:18px;pointer-events:none}
  .hud h1{font-size:17px;margin:0 0 4px;color:#89b4fa;font-weight:600}
  .hud p{margin:0;font-size:12px;color:#7f849c}
  .tip{position:fixed;max-width:300px;background:#181825ee;border:1px solid #45475a;border-radius:8px;
       padding:8px 11px;font-size:12.5px;display:none;pointer-events:none;z-index:9}
  .tip .k{color:#f9e2af;font-size:11px;margin-right:6px}
  .legend{position:fixed;right:16px;top:14px;font-size:11.5px;color:#7f849c;text-align:right}
  .legend b{display:inline-block;width:8px;height:8px;border-radius:50%;margin-left:6px;vertical-align:-1px}
</style></head><body>
<canvas id="c"></canvas>
<div class="hud"><h1>大肥鱼·记忆星图</h1><p>__STATS__</p></div>
<div class="legend">对话<b style="background:#89b4fa"></b> 观察<b style="background:#94e2d5"></b> 事实<b style="background:#cba6f7"></b> 里程碑<b style="background:#f9e2af"></b> 其他<b style="background:#6c7086"></b> 讲过的<b style="background:#f9e2af;box-shadow:0 0 6px #f9e2af"></b></div>
<div class="tip" id="tip"></div>
<script>
const NODES=__NODES__, LINKS=__LINKS__;
const RECALLED=new Set(__RECALLED__);
const KINDC={dialogue:'#89b4fa',observation:'#94e2d5',fact:'#cba6f7',milestone:'#f9e2af'};
const cv=document.getElementById('c'),ctx=cv.getContext('2d');
let W,H;function fit(){W=cv.width=innerWidth;H=cv.height=innerHeight}fit();onresize=fit;
// 初始布局：按 id 螺旋铺开，再跑几百步轻量斥力+连线引力，让它自己长成星云
const P={};const T0=Date.parse(NODES.length?NODES[NODES.length-1].ts:0)||0;
NODES.forEach((n,i)=>{const a=i*2.39996,r=30+14*Math.sqrt(i);
  P[n.id]={x:W/2+r*Math.cos(a),y:H/2+r*Math.sin(a),vx:0,vy:0,n};});
const age=n=>{const t=Date.parse(n.ts)||T0;return Math.max(0.08,Math.min(1,0.15+0.85*(t-(T0-6e8))/6e8))};
for(let it=0;it<260;it++){
  for(const i of NODES)for(const j of NODES){if(i.id>=j.id)continue;
    const a=P[i.id],b=P[j.id];let dx=b.x-a.x,dy=b.y-a.y,d2=dx*dx+dy*dy+40;
    const f=2600/d2;dx*=f;dy*=f;a.vx-=dx;a.vy-=dy;b.vx+=dx;b.vy+=dy;}
  for(const l of LINKS){const a=P[l.a],b=P[l.b];if(!a||!b)continue;
    let dx=b.x-a.x,dy=b.y-a.y;const d=Math.sqrt(dx*dx+dy*dy)||1;
    const f=(d-46)*0.004*Math.min(2,l.w);dx*=f;dy*=f;a.vx+=dx;a.vy+=dy;b.vx-=dx;b.vy-=dy;}
  for(const id in P){const p=P[id];p.vx*=0.82;p.vy*=0.82;
    p.x+=Math.max(-12,Math.min(12,p.vx));p.y+=Math.max(-12,Math.min(12,p.vy));}
}
let hover=null,sel=null,lastMouse={x:0,y:0};
cv.onmousemove=e=>{lastMouse={x:e.x,y:e.y};
  hover=null;for(const id in P){const p=P[id],n=p.n;
    if((e.x-p.x)**2+(e.y-p.y)**2<(4+n.s*3)**2){hover=n;break;}}
  cv.style.cursor=hover?'pointer':'default';};
cv.onclick=()=>{sel=(hover&&sel!==hover)?hover:null;};
const tipEl=document.getElementById('tip');
function tip(){const n=hover||sel;
  if(!n){tipEl.style.display='none';return;}
  tipEl.style.display='block';
  tipEl.innerHTML='<span class=\"k\">'+n.kind+'</span>'+'强度 '+n.s.toFixed(2)+' · '+n.ts.slice(5,16)+'<br>'+n.text;
  tipEl.style.left=Math.min(innerWidth-310,lastMouse.x+14)+'px';
  tipEl.style.top=(lastMouse.y+14)+'px';}
setInterval(tip,80);
function draw(){
  ctx.fillStyle='#0b1020';ctx.fillRect(0,0,W,H);
  const near=id=>{if(!sel)return true;return id==sel.id||LINKS.some(l=>(l.a==sel.id&&l.b==id)||(l.b==sel.id&&l.a==id));};
  for(const l of LINKS){const a=P[l.a],b=P[l.b];if(!a||!b)continue;
    if(sel&&!(l.a==sel.id||l.b==sel.id))continue;
    ctx.strokeStyle='rgba(137,180,250,'+(0.05+0.16*Math.min(1,l.w/3))+')';
    ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();}
  for(const n of NODES){const p=P[n.id];if(!p)continue;if(!near(n.id))continue;
    const r=2.5+Math.min(9,n.s*2.6);
    ctx.globalAlpha=age(n);
    ctx.fillStyle=KINDC[n.kind]||'#6c7086';
    ctx.beginPath();ctx.arc(p.x,p.y,r,0,7);ctx.fill();
    // 「想起」联动：她讲过的记忆会亮——金色脉冲环（讲过的记忆在她的星空里发光）
    if(RECALLED.has(n.id)){
      const pu=(Math.sin(Date.now()/420)+1)/2;
      ctx.strokeStyle='rgba(249,226,175,'+(0.35+0.55*pu).toFixed(2)+')';
      ctx.lineWidth=1.4;
      ctx.beginPath();ctx.arc(p.x,p.y,r+3.5+2.2*pu,0,7);ctx.stroke();
    }
    if(sel===n||hover===n){ctx.strokeStyle='#f5c2e7';ctx.lineWidth=1.5;
      ctx.beginPath();ctx.arc(p.x,p.y,r+3,0,7);ctx.stroke();}
    ctx.globalAlpha=1;}
  requestAnimationFrame(draw);
}
draw();
</script></body></html>""".replace("__NODES__", nodes_js).replace("__LINKS__", links_js)
             .replace("__RECALLED__", _json.dumps(soul._load_state().get("recent_recalled", [])))
             .replace("__STATS__", f"{n} 条记忆 · {len(links)} 条联想 · 从 {nodes[0][1][:10] if nodes else '—'} 到 {t_max[:10] if t_max else '—'}"))


@app.get("/starmap")
def starmap(request: Request):
    if not _lan_ok(request):
        return JSONResponse({"error": "need lan token"}, status_code=403)
    """她的记忆星图——浏览器直接看，数据实时从记忆库取"""
    from fastapi.responses import HTMLResponse


@app.get("/monitor/data")
def monitor_data(request: Request):
    if not _lan_ok(request):
        return JSONResponse({"error": "need lan token"}, status_code=403)
    """监测仪表盘数据（X7）：健康/账单/对话/记忆/提醒/心情，一次给全"""
    import sqlite3
    from datetime import datetime as _dt
    st = soul._load_state()
    today = date.today().isoformat()
    data = {"now": _dt.now().strftime("%H:%M:%S"), "mood": st.get("mood", 60),
            "rice_total": st.get("rice_total", 0), "chat_count": st.get("chat_count", 0),
            "token_ledger": st.get("token_ledger", {}),
            "mood_history": st.get("mood_history", [])[-80:],
            "latency_recent": list(LATENCY_LOG),
            "recent_recalled": st.get("recent_recalled", [])[:12],
            "reminders_pending": len(st.get("reminders", [])),
            "reminders_sent": st.get("reminders_sent", [])[-8:],
            "style_note": st.get("style_note", "")}
    try:
        conn = soul._db()
        q = lambda sql, *p: conn.execute(sql, p).fetchone()[0]
        data["msgs_today"] = q("SELECT COUNT(*) FROM messages WHERE ts LIKE ?", today + "%")
        data["user_today"] = q("SELECT COUNT(*) FROM messages WHERE ts LIKE ? AND role='user'", today + "%")
        data["msgs_total"] = q("SELECT COUNT(*) FROM messages")
        data["last_reflection"] = conn.execute(
            "SELECT substr(text,1,60) FROM messages WHERE role='reflection' ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
    except Exception as e:
        data["db_err"] = str(e)[:80]
    try:
        mconn = soul._mem()
        mq = lambda sql, *p: mconn.execute(sql, p).fetchone()[0]
        data["nodes_total"] = mq("SELECT COUNT(*) FROM nodes")
        data["nodes_today"] = mq("SELECT COUNT(*) FROM nodes WHERE ts >= ?", today + "T00:00")
        data["kinds"] = dict(mconn.execute("SELECT kind, COUNT(*) FROM nodes GROUP BY kind").fetchall())
        rid = data["recent_recalled"]
        if rid:
            marks = ",".join("?" * len(rid))
            data["recalled_texts"] = [r[0] for r in mconn.execute(
                "SELECT content FROM nodes WHERE id IN (%s)" % marks, rid)]
        else:
            data["recalled_texts"] = []
        mconn.close()
    except Exception as e:
        data["db_err"] = (data.get("db_err", "") + " | " + str(e)[:80])
    # 服务健康（从本进程探测另外两个）
    import urllib.request as _ur
    op = _ur.build_opener(_ur.ProxyHandler({}))
    def _up(u):
        try:
            op.open(u, timeout=1.5); return True
        except Exception:
            return False
    data["svc"] = {"server": True, "page": _up("http://127.0.0.1:8080/"),
                   "local_brain": _up("http://127.0.0.1:11434/")}
    return data


@app.get("/monitor")
def monitor(request: Request):
    if not _lan_ok(request):
        return JSONResponse({"error": "need lan token"}, status_code=403)
    """监测仪表盘：她活着的每一项指标，3 秒一刷"""
    from fastapi.responses import HTMLResponse
    return HTMLResponse("""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>小飞鱼·监测台</title><style>
  html,body{margin:0;min-height:100%;background:#0b1020;color:#cdd6f4;font:14px/1.6 system-ui,'Microsoft YaHei'}
  .wrap{max-width:1060px;margin:0 auto;padding:22px 18px}
  h1{font-size:18px;margin:0 0 2px;color:#89b4fa}
  .sub{font-size:12px;color:#7f849c;margin-bottom:16px}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:14px}
  .card{background:#11141f;border:1px solid #2a2f42;border-radius:12px;padding:14px 16px}
  .card h3{margin:0 0 8px;font-size:13px;color:#a6adc8;font-weight:600}
  .big{font-size:26px;font-weight:600;color:#cdd6f4;line-height:1.2}
  .dim{color:#7f849c;font-size:12px}
  .dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px;vertical-align:0}
  .on{background:#a6e3a1}.off{background:#f38ba8}
  table{width:100%;border-collapse:collapse;font-size:12.5px}
  td,th{padding:3px 4px;text-align:left;border-bottom:1px solid #232637}
  th{color:#7f849c;font-weight:400}
  .rec{color:#f9e2af;font-size:12.5px;line-height:1.8}
  canvas{width:100%;height:70px}
  .note{font-size:12px;color:#a6adc8;background:#181825;border-radius:8px;padding:8px 10px;margin-top:6px}
</style></head><body><div class="wrap">
<h1>小飞鱼 · 监测台</h1>
<div class="sub">每 3 秒自动刷新 · 数据全部来自本机</div>
<div class="grid">
  <div class="card"><h3>服务健康</h3><div id="svc"></div></div>
  <div class="card"><h3>今日对话</h3><div class="big" id="msgs">—</div><div class="dim" id="msgsd"></div></div>
  <div class="card"><h3>Token 账单（白饭消耗）</h3><div id="tok">—</div></div>
  <div class="card"><h3>记忆生态</h3><div id="mem">—</div></div>
  <div class="card"><h3>她讲过的记忆（「想起」）</h3><div class="rec" id="rec">还没有讲过</div></div>
  <div class="card"><h3>提醒</h3><div id="rem">—</div></div>
  <div class="card" style="grid-column:1/-1"><h3>实时延迟（最近几轮，秒）</h3><div id="lat">—</div></div>
  <div class="card" style="grid-column:1/-1"><h3>心情曲线（从今天开始记录）</h3><canvas id="mh" width="1000" height="70"></canvas></div>
  <div class="card" style="grid-column:1/-1"><h3>她最近的反思</h3><div class="note" id="refl">—</div></div>
</div></div>
<script>
function esc(s){return String(s).replace(/[<>&]/g,c=>({'<':'<','>':'>','&':'&'}[c]))}
async function tick(){
  try{
    const d = await (await fetch('/monitor/data',{cache:'no-store'})).json();
    const sv=d.svc||{};
    document.getElementById('svc').innerHTML =
      '<div class="big"><span class="dot on"></span>大脑服务在线</div><div class="dim" style="margin-top:6px">'+
      '<span class="dot '+(sv.page?'on':'off')+'"></span>页面服务 8080　'+
      '<span class="dot '+(sv.local_brain?'on':'off')+'"></span>本地脑 11434（离线兜底）</div>';
    document.getElementById('msgs').textContent = d.msgs_today + ' 条消息 / ' + d.user_today + ' 轮';
    document.getElementById('msgsd').textContent = '累计 ' + d.msgs_total + ' 条 · 心情 ' + d.mood + '/100 · 白饭 ' + d.rice_total + ' 碗 · 总轮数 ' + d.chat_count;
    const tl=d.token_ledger||{};let th='',sum=0;
    for(const day of Object.keys(tl).sort()){
      const brains=tl[day];let daySum=0;
      for(const b in brains){daySum+=brains[b];th+='<tr><td>'+day+'</td><td>'+esc(b)+'</td><td style="text-align:right">'+brains[b]+'</td></tr>'}
      sum+=daySum;
    }
    const lr=d.latency_recent||[];
    document.getElementById('lat').innerHTML = lr.length
      ? lr.slice(-6).reverse().map(function(x){return '<div class="dim">'+x.at+' 首字 '+
          (x.first_token===null?'—':x.first_token+'s')+' · 出声 '+
          (x.first_audio===undefined||x.first_audio===null?'—':x.first_audio+'s')+
          ' · 全程 '+x.total+'s · '+x.segments+' 句</div>';}).join('')
      : '还没有对话';
    document.getElementById('tok').innerHTML='<div class="big">'+sum+'</div><div class="dim">今日+历史，按脑分账（单位≈token）</div><table><tr><th>日期</th><th>脑子</th><th>消耗</th></tr>'+th+'</table>';
    const k=d.kinds||{};
    document.getElementById('mem').innerHTML='<div class="big">'+d.nodes_total+'</div><div class="dim">今日新增 '+d.nodes_today+' 条 · 对话 '+
      (k.dialogue||0)+' · 观察 '+(k.observation||0)+' · 事实 '+(k.fact||0)+' · 里程碑 '+(k.milestone||0)+'</div>';
    const rt=d.recalled_texts||[];
    document.getElementById('rec').innerHTML = rt.length? rt.map(t=>'· '+esc(t)).join('<br>') : '还没有讲过';
    const rs=d.reminders_sent||[];
    document.getElementById('rem').innerHTML='<div class="big">'+d.reminders_pending+'</div><div class="dim">条待发提醒</div>'+
      (rs.length?'<table>'+rs.map(r=>'<tr><td>'+r[0].slice(5,16)+'</td><td>'+esc(r[1])+'</td></tr>').join('')+'</table>':'<div class="dim" style="margin-top:6px">还没送过</div>');
    const cv=document.getElementById('mh'),ctx=cv.getContext('2d');
    ctx.clearRect(0,0,cv.width,cv.height);
    const h=d.mood_history||[];
    if(h.length>1){
      ctx.strokeStyle='#89b4fa';ctx.lineWidth=2;ctx.beginPath();
      h.forEach((pt,i)=>{const x=i/(h.length-1)*(cv.width-16)+8,y=cv.height-8-(pt[1]/100)*(cv.height-16);i?ctx.lineTo(x,y):ctx.moveTo(x,y)});
      ctx.stroke();
      const last=h[h.length-1];
      ctx.fillStyle='#f9e2af';ctx.font='12px system-ui';
      ctx.fillText('最新心情 '+last[1],cv.width-96,14);
    } else { ctx.fillStyle='#7f849c';ctx.font='12px system-ui';ctx.fillText('数据从今天开始积累，聊几轮就会长出曲线',12,40); }
    document.getElementById('refl').textContent = d.last_reflection? d.last_reflection[0] : '还没到反思时间（每晚 4 点）';
    document.getElementById('refl').textContent += d.style_note? ('　|　风格备注：'+d.style_note):'';
  }catch(e){}
}
tick();setInterval(tick,3000);
</script></body></html>""")


@app.get("/starmap")
def starmap(request: Request):
    if not _lan_ok(request):
        return JSONResponse({"error": "need lan token"}, status_code=403)
    """她的记忆星图——浏览器直接看，数据实时从记忆库取"""
    from fastapi.responses import HTMLResponse
    return HTMLResponse(_starmap_html())


LIVE_WS = set()   # 在线连接注册表：提醒推送器用（X4 送达保障，审计后新增）

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    if not _lan_ok(ws):
        await ws.close(code=4401)
        return
    await ws.accept()
    LIVE_WS.add(ws)
    st = soul._load_state()
    session_start = time.time()
    reminded_rest = False
    await ws.send_json({"type": "hello",
                        "msg": "本鲸上线了，白饭拿来",
                        "state": {"days": (date.today() - date.fromisoformat(st["birthday"])).days + 1,
                                  "mood": st["mood"], "rice_today": st["rice_total"]}})
    gen_task = None
    _last_notice_at = 0.0     # 打断提示限流用：45 秒内不重复说"等等等等"
    gen_state = {"partial": "", "abort": False}   # abort=协作式打断旗（不硬掐，防帧流撕裂）
    speech_round = 0    # 回合号：每开一轮说话 +1，所有带声音的消息都盖上。
                        # 前端只认当前回合，旧回合的消息到达即扔——
                        # 这是最后一道闸，不管哪条链路漏了旧音频都兜得住。

    async def wssend(payload):
        """带日志的安全发送：定位连接异常"""
        try:
            await ws.send_json(payload)
        except Exception as e:
            print("[ERR] ws send fail:", type(e).__name__, str(e)[:120], file=sys.stderr)
            raise

    async def send(payload):
        """回合号盖章的默认外发（循环层用，盖章时取当前回合）。process 内有自己的回合版。"""
        payload["r"] = speech_round
        await wssend(payload)




    async def process(packet, rnd=None):
        """单条消息的完整处理（可被打断）"""
        if rnd is None:
            rnd = speech_round
        async def send(payload):
            # 本回合的所有外发都走这里：盖上回合号
            payload["r"] = rnd
            await wssend(payload)
        nonlocal st, reminded_rest

        # ===== 视觉：知道你在，不分析画面 =====
        # 前端不再上传截图。她不需要"看懂"你在干什么——转过头看着你这件事
        # 在前端本地靠人脸坐标就做完了。这里只负责"看见你回来了"这一句招呼。
        # 要是以后真要让她看东西，前端把 image 带上就会走下面的 VLM 分支。
        if packet.get("type") == "look":
            img64 = (packet.get("image") or "").split(",")[-1]
            if not img64:
                reaction = random.choice([
                    "哟，回来了。",
                    "使用者回来了？本鲸看见你了。",
                    "人在这儿呢，本鲸一直看着。",
                    "回来啦。站那么远干嘛。",
                ])
                audio = await tts_base64(reaction)
                await send({"type": "sight", "text": reaction, "audio": audio})
                return
            reaction = None
            try:
                reaction = vl_look(img64)
            except Exception as e:
                print("[WARN] VL 不可用，光影分析兜底:", str(e)[:80], file=sys.stderr)
            if not reaction:
                reaction = demo_look(img64)
            # 看到的这一眼不进记忆流。进了就会被反复召回，
            # 于是你正经问个事，她冷不丁提一句"你窗帘"——注意力全跑偏了。
            audio = await tts_base64(reaction)
            await send({"type": "sight", "text": reaction, "audio": audio})
            return

        # ===== 建一次"你的样子"的档 =====
        # 前端只在第一次稳稳定定看见人时发一次。写进 portrait 之后，
        # build_context 每次都会带上去，她就"知道"你长什么样了。
        if packet.get("type") == "remember_face":
            img64 = (packet.get("image") or "").split(",")[-1]
            if not img64:
                return
            try:
                desc = vl_remember_face(img64)
            except Exception as e:
                print("[WARN] 长相建档失败:", str(e)[:100], file=sys.stderr)
                return
            if desc:
                soul.portrait_update("长相", desc)
                _dbg("face archived", desc[:40])
                line = "记住了。你长什么样，本鲸存下来了。"
                await send({"type": "sight", "text": line,
                              "audio": await tts_base64(line)})
            return

        # ===== 她自己开口 =====
        if packet.get("type") == "proactive":
            # 到期的提醒先于闲聊（工具层 X4 的执行通道：借用空闲搭话轮询）
            due = soul.due_reminder()
            if due:
                text = "使用者，你之前让我提醒你的：{0}。到点了！".format(due["what"])
                emo = "happy"
                _dbg("提醒送达:", due["what"][:40])
            else:
                text, emo = proactive_line()
                emo = emo or "happy"
            audio = await tts_base64(text)
            await send({"type": "reply", "text": text, "emotion": emo,
                          "action": "none", "rice_today": st["rice_total"],
                          "mood": st["mood"], "milestone": [],
                          "latency": 0, "first_out": 0, "audio": audio,
                          "proactive": True, "reminder": bool(due)})
            soul.log_message("assistant", text, emo, "none", 0)
            return

        if packet.get("type") != "text":
            return
        user_text = packet.get("data", "")
        if not user_text:
            return
        soul.log_message("user", user_text)
        soul.memorize("dialogue", "使用者说：" + user_text)

        # 护栏 1：危机响应（最高优先级）
        if soul.crisis_check(user_text):
            soul.portrait_update("需要关注", "使用者说过让人担心的话，要多陪他、多留意")
            text = soul.CRISIS_REPLY
            audio = await tts_base64(text)
            await send({"type": "reply", "text": text, "emotion": "认真",
                          "action": "none", "rice_today": st["rice_total"],
                          "mood": st["mood"], "crisis": True, "audio": audio})
            return

        # 护栏 2：每日预算
        if budget_check():
            text = "今天的白饭配额用完了，本鲸先消化消化。明天再来，白饭管够。"
            await send({"type": "reply", "text": text, "emotion": "瞌睡",
                          "action": "sleep", "rice_today": st["rice_total"],
                          "mood": st["mood"], "budget": True})
            return

        # 画像自动更新
        m_like = re.search(r"(?:我最?喜欢|我爱)(.{1,12}?)(?:[，。！！？?~\s]|$)", user_text)
        if m_like:
            soul.portrait_update("喜好", m_like.group(1).strip().rstrip("了呀呢哦哈"))
        m_hate = re.search(r"(?:我讨厌|我不喜欢|我最讨厌)(.{1,12}?)(?:[，。！！？?~\s]|$)", user_text)
        if m_hate:
            soul.portrait_update("雷区", m_hate.group(1).strip().rstrip("了呀呢哦哈"))
        if user_text.startswith("记住"):
            soul.add_fact(user_text[2:].strip("：: ，,"))

        # 神经链条：每句话成为记忆节点
        soul.memorize("dialogue", "使用者说：" + user_text)
        # 攒够十几句就让后台归纳一次画像（不阻塞这条回复）
        kick_portrait()

        # ===== 流式生成：字蹦出来就往前台推（体感提速 10 倍）=====
        if BRAIN_MODE == "cloud" and CLOUD is not None:
            context = soul.build_context(user_text)
            t0 = time.time()
            full, first_out, last_err = "", None, None
            _mood = soul._load_state().get("mood", 60)
            # 通道同时起跑，谁先吐字用谁；七秒连不上就不等它了
            stream_it, _pending, _prov_name = None, None, None
            try:
                stream_it, _pending, _prov_name = await race_first_token(
                    CLOUD["providers"],
                    build_messages(context, user_text),
                    mood_token_budget(_mood),
                    hedge_after=8.0)   # 英伟达是正主：给它 8 秒先跑，不出字才轮到硅基备胎
            except Exception as e:
                last_err = e
            _dbg("race", _prov_name or "-", round(time.time() - t0, 2), "s",
                 "ERR " + type(last_err).__name__ if last_err else "")
            if stream_it is None:
                # 云端全挂（断网/欠费/接口爆炸）：本地兜底脑顶上——
                # ollama 跑本地模型，慢一点但她永远不会变成哑巴（智能韧性层）。
                _dbg("cloud all dead, try local brain")
                try:
                    local_brain = OpenAI(api_key="local", base_url=LOCAL_BRAIN_URL, timeout=300)
                    stream_it = local_brain.chat.completions.create(
                        model=LOCAL_BRAIN_MODEL, messages=build_messages(context, user_text),
                        max_tokens=mood_token_budget(_mood), temperature=1.0, stream=True)
                    _prov_name = "local"
                except Exception as e2:
                    _dbg("local brain also fail:", str(e2)[:80])
            if stream_it is None:
                _dbg("model unreachable", type(last_err).__name__, str(last_err)[:100])
                await send({"type": "reply",
                              "text": "本鲸这边卡住了，脑子没转过来。你再说一遍？",
                              "emotion": "委屈", "action": "none",
                              "rice_today": st["rice_total"], "mood": st["mood"],
                              "milestone": [], "latency": 0, "first_out": 0,
                              "audio": await tts_base64("本鲸卡住了。你再说一遍？")})
                return

            # 边说边合成：切出一句就丢给 TTS，第一句好了就能出声，
            # 不用等整段说完。原来要等 LLM 全生成完再整段合成，一句话能等十几秒。
            audio_q = asyncio.Queue()

            # 卡壳的病根：单个合成工人是"合一句、发一句、再合下一句"，
            # 上一句念完了下一句还在合成——那段空档她就是哑的。
            # 现在开两个工人并行合成，发送端按编号排序发，顺序不乱。
            TTS_WORKERS = 2
            done_q = asyncio.Queue()

            async def _tts_worker():
                while True:
                    item = await audio_q.get()
                    if item is None:
                        _dbg("tts worker exit")
                        await done_q.put(None)
                        return
                    idx, seg = item
                    if gen_state["abort"]:
                        # 被打断了：队列里剩下的全是上一轮的话，直接扔
                        continue
                    _t = time.time()
                    a = await tts_base64(seg)
                    if not a:
                        # TTS 偶发抽风一次，重试一拍；不然这句话就哑了，
                        # 表现就是"她有时候说话没声音"。
                        await asyncio.sleep(0.3)
                        a = await tts_base64(seg)
                    _dbg("tts seg", idx, len(seg), "ok" if a else "NONE", round(time.time() - _t, 2))
                    if a and not gen_state["abort"]:
                        await done_q.put((idx, a, clean_for_tts(seg)))

            async def _speak_sender():
                nxt = 0
                buf = {}
                alive = TTS_WORKERS
                while alive > 0:
                    item = await done_q.get()
                    if item is None:
                        alive -= 1
                        continue
                    idx, a, txt = item
                    if gen_state["abort"]:
                        continue
                    buf[idx] = (a, txt)
                    # 编号连续就按序发，保证字和声音的顺序永远不乱
                    while nxt in buf:
                        a2, txt2 = buf.pop(nxt)
                        if "first_audio" not in gen_state:
                            gen_state["first_audio"] = round(time.time() - t0, 2)
                        await send({"type": "audio", "data": a2, "text": txt2})
                        nxt += 1

            workers = [asyncio.create_task(_tts_worker()) for _ in range(TTS_WORKERS)]
            sender = asyncio.create_task(_speak_sender())
            buf = ""
            # 心情摆烂的时候只说一句。声音也得短，不能光截字幕
            _low_mood = soul._load_state().get("mood", 60) < 40
            _spoken = 0
            _dbg_t = time.time()
            _stream_it = stream_it
            try:
                while True:
                    if gen_state["abort"]:        # 协作式打断：安全点退出，不撕帧
                        break
                    try:
                        if _pending is not None:
                            # 竞速时已经抢到的那一段，先用掉，别再等一次
                            delta, _pending = _pending, None
                        else:
                            # 出了字之后每帧等 12 秒，卡住就收工
                            chunk = await asyncio.wait_for(
                                _stream_it.__anext__(),
                                timeout=12)
                            try:
                                delta = chunk.choices[0].delta.content or ""
                            except Exception:
                                delta = ""
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        _dbg("stream timeout, first_out=", first_out)
                        break
                    if not delta:
                        continue
                    if first_out is None:
                        first_out = round(time.time() - t0, 2)
                        print(f"[DBG] first token {first_out}s", file=sys.stderr)
                        await send({"type": "chunk_start"})
                    full += delta
                    gen_state["partial"] = full
                    await send({"type": "chunk", "text": delta})
                    buf += delta
                    while True:
                        seg, buf = _cut_sentence(buf, quick=(_spoken == 0 and QUICK_FIRST))
                        if seg is None:
                            break
                        if _low_mood and _spoken >= 1:
                            buf = ""
                            break
                        audio_q.put_nowait((_spoken, seg))
                        _spoken += 1
                if buf.strip() and not gen_state["abort"] and len(buf.strip()) >= 5:
                    # 尾巴太短（"干饭～"这种）就不送去合成了：
                    # 三五个字的短句克隆出来音色最容易飘，听着像换了个人。
                    audio_q.put_nowait((_spoken, buf))
            finally:
                for _ in range(TTS_WORKERS):
                    audio_q.put_nowait(None)
                try:
                    await asyncio.wait_for(sender, timeout=30)
                except Exception:
                    sender.cancel()
                for w in workers:
                    if not w.done():
                        w.cancel()

            if gen_state["abort"]:
                return   # 被打断：静默退出，打断方负责人性化接话
            latency = round(time.time() - t0, 1)
            LATENCY_LOG.append({"at": time.strftime("%H:%M:%S"),
                                "first_token": first_out,
                                "first_audio": gen_state.get("first_audio"),
                                "total": latency, "segments": _spoken})
            _dbg("latency", "first_token", first_out, "first_audio",
                 gen_state.get("first_audio"), "total", latency, "segments", _spoken)
            text, emotion, action = parse_reply(full)
            if not text:
                text = "本鲸在，说吧。"
            if soul._load_state().get("mood", 60) < 40:
                text = cut_short(text)
            usage_est = len(full) * 2
            reply = {"text": text, "emotion": emotion, "action": action,
                     "rice_add": max(1, usage_est // 1000), "tokens": usage_est,
                     "latency": latency, "first_out": first_out, "spoken": True}
        else:
            reply = chat_with_dafeiyu(user_text)

        soul.log_message("assistant", reply["text"],
                         reply["emotion"], reply["action"], reply["tokens"])
        # ===== 工具层 v0（X4）：解析她回复末尾的 [tool: ...] 调用并执行 =====
        m_tool = re.search(r"\[tool:\s*([a-zA-Z_]+)\((.*)\)\]\s*$", reply["text"], re.S)
        if m_tool:
            tool_name, tool_args = m_tool.group(1), m_tool.group(2)
            reply["text"] = reply["text"][:m_tool.start()].rstrip()
            _dbg("tool call:", tool_name, tool_args[:60])
            try:
                if tool_name == "remind":
                    mm = re.match(r"\s*(\d+(?:\.\d+)?)\s*[，,]?\s*(.*)", tool_args, re.S)
                    if mm:
                        r_ = soul.reminder_set(float(mm.group(1)), mm.group(2))
                        _dbg("提醒已登记:", r_["what"][:40], "due", r_["due"])
                elif tool_name == "open_starmap":
                    import urllib.parse as _up
                    _url = 'http://127.0.0.1:8765/starmap'
                    _edge = next((p for p in (
                        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe") if os.path.exists(p)), None)
                    if _edge:
                        subprocess.Popen([_edge, '--app=' + _url],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        _dbg("星图已打开")
                    _dbg("星图已打开")
            except Exception as e:
                _dbg("tool 执行失败:", str(e)[:80])
        if m_tool:
            # log_message 发生在剥离之前，记忆库里存的是带调用行的脏文本；
            # 不修正的话，下一次检索会把 "[tool: remind(...)]" 当成她说的话召回。
            try:
                _c = soul._db()
                _c.execute("UPDATE messages SET text=? WHERE id=(SELECT MAX(id) FROM messages WHERE role='assistant')",
                           (reply["text"],))
                _c.commit()
                _c.close()
            except Exception:
                pass
        # 日记随聊随写：桌面那份永远反映今天的进度。原来只在凌晨 4 点写，
        # 服务端凌晨不在场那天就是空白页（老板 2026-11-08 点名）。
        try:
            await asyncio.to_thread(soul.write_diary)
        except Exception as e:
            _dbg("diary 随聊更新失败:", str(e)[:60])
        # 她的回复不再塞进记忆流：说过的话对话历史里已经有了，
        # 再存一份会在检索时被反复召回，等于让她对着自己复读。
        st = soul.apply_interaction(user_text, reply["emotion"], reply["tokens"])
        soul.budget_spend(reply["tokens"])
        # Token 账单（X5）：按天按脑记账，成本可见——谁花的、花了多少
        try:
            stx = soul._load_state()
            ledger = stx.setdefault("token_ledger", {})
            day = time.strftime("%Y-%m-%d")
            brain_key = (_prov_name or "chat")
            entry = ledger.setdefault(day, {})
            entry[brain_key] = entry.get(brain_key, 0) + reply.get("tokens", 0)
            soul._save_state(stx)
        except Exception as _le:
            _dbg("token 账单失败:", str(_le)[:60])
        milestones = soul.check_milestones()

        # 护栏 3：连续 60 分钟提醒
        rest_reminder = False
        if time.time() - session_start > 3600 and not reminded_rest:
            rest_reminder = True
            reminded_rest = True
        if rest_reminder:
            reply["text"] += "（本鲸得去睡了，你也该休息了，明天见）"

        # 流式那条路已经边生成边把音频发过去了，这里只兜底非流式
        audio = None if reply.get("spoken") else await tts_base64(reply["text"])
        await send({"type": "reply",
                      "text": reply["text"],
                      "emotion": reply["emotion"],
                      "action": reply["action"],
                      "rice_today": st["rice_total"],
                      "mood": st["mood"],
                      "milestone": milestones,
                      "latency": reply.get("latency"),
                      "first_out": reply.get("first_out"),
                      "audio": audio})

    def _task_done(t):
        if not t.cancelled() and t.exception():
            import traceback as _tb
            e = t.exception()
            _dbg("TASK ERR", repr(e))
            # format_exc() 只能在 except 块里用，这里没有活动异常，之前一直打 "NoneType: None"，
            # 等于什么都没记。要拿到真栈得自己拼。
            try:
                _dbg("".join(_tb.format_exception(type(e), e, e.__traceback__))[:800])
            except Exception:
                pass
            print("[ERR] process:", e, file=sys.stderr)

    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") != "websocket.receive":
                continue
            raw = msg.get("text") or ""
            try:
                packet = json.loads(raw)
            except json.JSONDecodeError:
                packet = {"type": "text", "data": raw}
            if packet.get("type") not in ("text", "look", "proactive", "remember_face", "clog", "daydream", "feedback"):
                continue
            if packet.get("type") == "feedback":
                bad = soul.mark_bad_reply()
                _dbg("feedback 负样本:", (bad or "")[:40])
                await send({"type": "feedback_ok", "text": "记下了，这句以后不当教材。"})
                continue
            if packet.get("type") == "clog":
                # 客户端事件日志回传：连接断了以后，两边时间线在 dbg.log 里对得上
                for ln in packet.get("lines", []):
                    _dbg("[client]", ln)
                continue

            # ===== 「想起」：独处发呆时，她自己翻记忆讲旧事 =====
            # 客户端在她空闲时才会发这个包。深夜不起念头；随机三成半这次也
            # 不想起——定时器太规律就成了脚本，随机才像"自己忽然想起来"。
            if packet.get("type") == "daydream":
                hour = time.localtime().tm_hour   # 本机时区（北京时间）
                if 23 <= hour % 24 or hour % 24 < 7:
                    _dbg("daydream 抑制（深夜不起念头）")
                    continue
                if random.random() < 0.35:
                    _dbg("daydream 抑制（这次没想起）")
                    continue
                dd = soul.daydream()
                if not dd:
                    _dbg("daydream 没有 48h 前的可想记忆")
                    continue
                _dbg("daydream 命中:", dd["text"][:40])
                text = ""
                try:
                    resp = await asyncio.to_thread(
                        cloud_call,
                        "你正一个人发呆，忽然想起一件以前的事。基于「当时的话」和「想起的事」，"
                        "用本鲸的口吻主动说一句 30 字以内的话——像自己想起来的，自然一点，"
                        "不要解释你在干什么，不要提\"记忆库\"三个字。",
                        "（自言自语）")
                    text, emo, act = parse_reply((resp.choices[0].message.content or "").strip())
                except Exception as e:
                    _dbg("daydream LLM fail:", str(e)[:80])
                if not text:
                    text = "（本鲸发了一会儿呆，想起）" + dd["text"]
                    emo, act = "思考", "none"
                # 行为-记忆联动（B1）：想起的内容决定她此刻的情绪和动作——
                # 灵魂驱动身体，不是随机表演。
                _pos = ("开心", "喜欢", "高兴", "笑", "棒", "厉害", "好玩", "第一次连上", "看到我")
                _neg = ("哭", "疼", "怕", "咬死", "难过", "生气", "吵架", "认不出", "罪行")
                if any(w in dd["text"] for w in _neg):
                    emo, act = "serious", "none"          # 想起不好的事：沉下来
                elif any(w in dd["text"] for w in _pos):
                    emo, act = "happy", "wag_fast"        # 想起好事：尾巴摇起来
                soul.recall_mark(dd["id"])                # 星图联动地基：登记刚讲过的节点
                a = await tts_base64(text)
                payload = {"type": "reply", "text": text, "emotion": emo or "思考",
                           "action": act or "none", "recall": True}
                if a:
                    payload["audio"] = a
                await send(payload)
                continue

            # ===== 打断机制：只有用户真的开口才算打断 =====
            # text / look / proactive 三种包都走这条 receive 循环。原来不分类型，
            # 摄像头每几秒发一张 look 也会把正在生成的回复掐掉，还要白等最多 8 秒，
            # 于是她的话永远说不完——表现就是"怎么问她都不回"。见交接文档第十四节。
            busy = gen_task is not None and not gen_task.done()
            if packet.get("type") == "remember_face":
                # 建档单独跑，绝对不能碰 gen_task。
                # 原来它走 pass 落到下面那行，会把正在生成的 gen_task 直接覆盖掉——
                # 旧任务没人取消、继续往客户端吐字，新的也在吐，
                # 听起来就是"同一句话说了又说"。这是真 bug，不是模型抽风。
                # 但也不能直接并发跑：建档完的确认音会从同一条通道挤进
                # 她正在说的回复里。排队，等到"此刻她没在说"才动手；
                # 就算动手后又开了新话头，这条确认音带着旧回合号，
                # 前端到达即扔——最后一道闸保证不叠声。
                _r0 = speech_round
                async def _deferred_remember(p, _r):
                    try:
                        while True:
                            t = gen_task
                            if t is None or t.done():
                                break
                            try:
                                await asyncio.shield(t)
                            except Exception:
                                pass
                        await process(p, _r)
                    except Exception as e:
                        _dbg("remember ERR", repr(e)[:100])
                asyncio.create_task(_deferred_remember(packet, _r0))
                continue
            elif packet.get("type") != "text":
                if busy:
                    continue          # 视觉快照和主动行为不抢话，直接跳过这一包
            elif busy:
                gen_state["abort"] = True
                _dbg("interrupt", "旧回合作废，partial", len(gen_state.get("partial", "")), "字")
                try:
                    await asyncio.wait_for(asyncio.shield(gen_task), timeout=8)
                except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                    pass
                gen_state["abort"] = False
                if not gen_task.done():
                    # 网络卡死等极端情况：主动关闭连接让客户端重连（好过撕裂帧流）
                    print("[WARN] 旧生成 8s 未退出，关闭连接让客户端重连", file=sys.stderr)
                    await ws.close()
                    return
                partial = gen_state.get("partial", "")
                if len(partial) > 15:
                    snippet = partial[:10] + "……"
                    lines = [f"等等等等，本鲸刚才正说到「{snippet}」——好好好，你先说，说完本鲸接着唠。",
                             f"哎哎哎，本鲸话都说一半了……行行行，你最新的这条优先，刚才那半句本鲸记着呢。"]
                else:
                    lines = ["哎，本鲸刚张嘴你就抢话——说吧说吧，你先请，本鲸听着。",
                             "等等，本鲸话还没成句呢……行，你先说，本鲸记性好，一会儿接上。"]
                notice = random.choice(lines)
                if partial:
                    soul.memorize("observation", "本鲸被打断时正想说：" + partial)
                # 打断提示限流：连环打断时"等等等等"刷屏本身就是废话（老板 2026-11-07 点名）
                if time.time() - _last_notice_at > 45:
                    _last_notice_at = time.time()
                    await send({"type": "notice", "text": notice})
                    _dbg("notice", notice[:40])
                else:
                    _dbg("notice 抑制（45s 内已说过）", notice[:30])
            speech_round += 1                     # 新回合开讲：旧回合的一切从此作废
            gen_task = asyncio.create_task(process(packet, speech_round))
            gen_task.add_done_callback(_task_done)
    except Exception as e:
        _dbg("WS LOOP EXIT", repr(e))
        LIVE_WS.discard(ws)
        pass  # 断线重连由客户端负责
