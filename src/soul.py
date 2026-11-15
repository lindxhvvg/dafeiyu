# 大肥鱼灵魂层 v0.1 —— 记忆 / 人格状态 / 成长里程碑 / 日记
# 纯标准库（sqlite3）+ 可选的本地向量模型（fastembed），模型不在也能跑。
#
# 设计原则（诚实的边界）：
#   这是"程序化人格"：记忆靠数据库，情绪靠状态变量，成长靠互动统计。
#   它不是意识，但体验上是"一个记得你、有心情、会长大"的角色，
#   与每次对话后失忆的聊天框是两种生物。

import json
import math
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "soul.db")
STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "soul_state.json")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BIRTHDAY = date.today().isoformat()  # 首次初始化的那天=她的生日

# ---------- 数据库 ----------
def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, role TEXT, text TEXT, emotion TEXT, action TEXT, tokens INTEGER)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS facts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, fact TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS diary(
        day TEXT PRIMARY KEY, content TEXT, chats INTEGER, rice INTEGER, mood INTEGER)""")
    return conn

# ---------- 状态文件 ----------
DEFAULT_STATE = {
    "birthday": BIRTHDAY,
    "mood": 60,        # 0-100，越高越活泼
    "trust": 10,       # 0-100，越高越黏人
    "rice_total": 0,   # 累计白饭（碗）
    "chat_count": 0,   # 累计对话轮数
    "last_seen": "",   # 最后互动日期
}

def _save_state(st):
    """先写临时文件再改名。直接覆盖写的话，写到一半断电/崩溃，
    留下一个半截 JSON，下次启动 _load_state 直接抛异常，整个服务起不来。"""
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATE_PATH)


def _load_state():
    """读状态。文件坏了不能让服务起不来——回退到默认值并备份坏文件。"""
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            sys.stderr.write("[WARN] 状态文件损坏，已备份并重建: %s\n" % str(e)[:80])
            try:
                os.replace(STATE_PATH, STATE_PATH + ".broken")
            except Exception:
                pass
    st = dict(DEFAULT_STATE)
    _save_state(st)
    return st

# ---------- 对话记录 ----------
def log_message(role, text, emotion="none", action="none", tokens=0):
    conn = _db()
    conn.execute("INSERT INTO messages(ts,role,text,emotion,action,tokens) VALUES(?,?,?,?,?,?)",
                 (datetime.now().isoformat(timespec="seconds"), role, text,
                  emotion, action, tokens))
    conn.commit()
    conn.close()

# ---------- 记忆检索：字符二元组重合度打分（中文够用的朴素方案） ----------
def _bigrams(s):
    s = "".join(ch for ch in s if ch.isalnum())
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s}

# ---------- 长期事实（"记住：xxx"） ----------
def add_fact(text):
    conn = _db()
    conn.execute("INSERT INTO facts(ts,fact) VALUES(?,?)",
                 (datetime.now().isoformat(timespec="seconds"), text))
    conn.commit()
    conn.close()

def all_facts():
    conn = _db()
    rows = conn.execute("SELECT fact FROM facts ORDER BY id DESC LIMIT 20").fetchall()
    conn.close()
    return [r[0] for r in rows]

# ---------- 互动反馈：情绪事件驱动人格状态 ----------
def apply_interaction(user_text, reply_emotion, tokens):
    st = _load_state()
    st["chat_count"] += 1
    st["rice_total"] += max(1, round(tokens / 1000)) if tokens else 1
    st["last_seen"] = date.today().isoformat()

    t = user_text or ""
    # 触发规则（全部透明可查，就在这一段里）
    if any(w in t for w in ("胖", "肥", "蠢")):
        st["mood"] = max(0, st["mood"] - 8)     # 被说胖→炸毛
        st["trust"] = max(0, st["trust"] - 1)
    if any(w in t for w in ("棒", "厉害", "喜欢你", "可爱", "夸")):
        st["mood"] = min(100, st["mood"] + 6)   # 被夸→开心
        st["trust"] = min(100, st["trust"] + 2)
    if "白饭" in t or "喂" in t:
        st["mood"] = min(100, st["mood"] + 10)  # 喂饭→最开心
    # 情绪向基线回归（60=平时）
    st["mood"] += (60 - st["mood"]) // 10
    # 心情历史（监测系统用）：最多留 200 个点
    hist = st.get("mood_history", [])
    hist.append([datetime.now().isoformat(timespec="seconds"), st["mood"]])
    st["mood_history"] = hist[-200:]
    _save_state(st)
    return st

# ---------- 注入 system 的人格状态段 ----------
def daydream():
    """独处时自主想起：从两天前的旧记忆里挑一件讲出来。
    打分 = 记忆强度 + 与最近对话的字面关联（想起的事常和今天有点关系）。
    讲出来后节点强化（赫布：说出来的话活得久），24 小时内提过的不重复。
    返回 {id, seed, text}；没有可想起的就返回 None。"""
    conn = _mem()
    now = datetime.now()
    cutoff = (now - timedelta(days=2)).isoformat(timespec="seconds")
    rows = conn.execute(
        "SELECT id, ts, kind, content, strength, last_recalled FROM nodes "
        "WHERE kind IN ('dialogue','observation') AND ts < ? AND content != '' "
        "ORDER BY id DESC LIMIT 120", (cutoff,)).fetchall()
    if not rows:
        conn.close()
        return None
    recent = [c for _, c in conn.execute(
        "SELECT id, content FROM nodes WHERE kind='dialogue' "
        "ORDER BY id DESC LIMIT 6").fetchall()]
    # 内容级去重：同文案可能存了多个节点，按 id 去重挡不住换号重来
    recalled_recent = {c for (c,) in conn.execute(
        "SELECT content FROM nodes WHERE last_recalled IS NOT NULL AND last_recalled >= ?",
        ((now - timedelta(hours=24)).isoformat(timespec="seconds"),)).fetchall()}
    conn.close()
    rq = _bigrams("".join(recent))
    best = None
    for nid, ts, kind, content, S, last in rows:
        if last and (now - datetime.fromisoformat(last)).total_seconds() < 86400:
            continue                       # 24 小时内提过的不再重复
        if content in recalled_recent:
            continue                       # 同文案的兄弟节点也算提过
        age = (now - datetime.fromisoformat(ts)).total_seconds() / 86400
        overlap = len(rq & _bigrams(content)) / (len(rq) or 1)
        score = (S or 1) * 0.5 + overlap * 2.0 + age * 0.03 + (hash(content) % 100) / 100.0
        if best is None or score > best[0]:
            best = (score, nid, content, ts)
    if not best:
        conn.close()
        return None
    _, nid, content, ts = best
    now_iso = now.isoformat(timespec="seconds")
    conn = _mem()
    conn.execute("UPDATE nodes SET strength=strength+0.15, last_recalled=? WHERE id=?",
                 (now_iso, nid))
    conn.commit()
    conn.close()
    return {"id": nid, "seed": "（" + ts[:10] + "）" , "text": content}


def recall_mark(nid):
    """把刚讲过的记忆节点登记进状态（星图联动用：最近讲过的会亮）。"""
    st = _load_state()
    lst = st.get("recent_recalled", [])
    lst = [n for n in lst if n != nid]
    lst.insert(0, nid)
    st["recent_recalled"] = lst[:12]
    _save_state(st)


def persona_evolve():
    """人格演化 v0（风格漂移安全版）：从最近的对话里蒸馏"怎么说话"的偏好，
    生成一段 ≤160 字的风格备注注入对话。只影响措辞，不改身份骨架。
    可逆：清掉 soul_state.style_note 即回到默认人格。
    老板的构思：人格应该随经历的一切而更改——这是它的第一块砖。"""
    conn = _db()
    rows = conn.execute(
        "SELECT text FROM messages WHERE role='user' AND text != '' "
        "ORDER BY id DESC LIMIT 20").fetchall()
    conn.close()
    if len(rows) < 6:
        return None                      # 样本太少，先不动人格
    texts = [r[0] for r in rows]
    avg_len = sum(len(t) for t in texts) / len(texts)
    length_pref = "短句" if avg_len <= 8 else ("中等长度" if avg_len <= 20 else "长句子")
    nick = None
    for t in texts:
        for cand in ("小飞鱼", "大肥鱼", "肥鱼"):
            if cand in t:
                nick = cand
                break
        if nick:
            break
    freq = {}
    for t in texts:
        for bg in _bigrams(t):
            freq[bg] = freq.get(bg, 0) + 1
    top = [w for w, c in sorted(freq.items(), key=lambda kv: -kv[1]) if len(w) >= 2][:3]
    note = "使用者说话偏好%s，你也别啰嗦；" % length_pref
    if nick:
        note += "他现在叫你「%s」，你可以这么自称；" % nick
    if top:
        note += "他最近常聊：" + "、".join(top) + "，接话顺着这些来。"
    note = note[:160]
    st = _load_state()
    st["style_note"] = note
    st["style_updated"] = datetime.now().isoformat(timespec="seconds")
    _save_state(st)
    return note


def reminder_set(minutes, what):
    """登记一条提醒（工具层 X4 的手）：due 时间戳 + 内容，存 soul_state。"""
    st = _load_state()
    lst = st.get("reminders", [])
    lst.append({"due": (datetime.now() + timedelta(minutes=max(0.2, minutes))).isoformat(timespec="seconds"),
                "what": str(what)[:80]})
    st["reminders"] = lst
    _save_state(st)
    return lst[-1]

def due_reminder():
    """取一条到期的提醒（有就弹出返回，没有返回 None）。"""
    st = _load_state()
    lst = st.get("reminders", [])
    now = datetime.now()
    for i, r in enumerate(lst):
        if datetime.fromisoformat(r["due"]) <= now:
            lst.pop(i)
            st["reminders"] = lst
            _save_state(st)
            return r
    return None


def style_examples(limit=5):
    """从真实对话里挑「最像她」的问答对，当少样本教材。
    这不是改模型权重：教材全部来自她自己说过的话，本地、可逆、不联网。
    老板点「这句不像她」会写进 bad_replies，下次重算时排除。"""
    import re as _re
    st = _load_state()
    cache = st.get("style_examples_cache")
    if cache and cache.get("day") == date.today().isoformat() and cache.get("items"):
        return cache["items"][:limit]
    conn = _db()
    rows = conn.execute(
        "SELECT a.text, b.text FROM messages a JOIN messages b ON b.id = a.id + 1 "
        "WHERE a.role='user' AND b.role='assistant' ORDER BY b.id DESC LIMIT 400").fetchall()
    conn.close()
    bad = set(st.get("bad_replies", []))
    banned = ("测试", "审计", "推送器", "[tool:", "[emotion:", "[action:", "TODO", "http")
    scored, seen = [], set()
    for q, a in rows:
        q = (q or "").strip(); a = (a or "").strip()
        if not q or not (8 <= len(a) <= 60) or len(q) > 50:
            continue
        if a in bad or any(x in a for x in banned):
            continue
        if _re.search(r"[A-Za-z]{4,}", a):
            continue
        # 裸写的情绪词（"干饭～""思考～"）是标签泄漏，绝不能当教材
        if _re.search(r"(?:开心|委屈|炸毛|瞌睡|干饭|思考)(?:ing)?\s*[~～♪]", a):
            continue
        if _re.search(r"(?:开心|委屈|炸毛|瞌睡|干饭|思考)(?:ing)?[。！!\s]*$", a):
            continue
        if a[:6] in seen:
            continue
        seen.add(a[:6])
        score = 0
        score += 2 if any(w in a for w in ("本鲸", "白饭", "尾巴", "摸鱼")) else 0
        score += 1 if any(c in a for c in "？！~～") else 0
        score += 1 if 12 <= len(a) <= 34 else 0
        score -= 2 if a.startswith(("使用者，", "使用者你", "嗨，使用者")) else 0
        scored.append((score, q, a))
    scored.sort(key=lambda x: -x[0])
    items = [{"q": q[:40], "a": a[:60]} for _, q, a in scored[:12]]
    st["style_examples_cache"] = {"day": date.today().isoformat(), "items": items}
    _save_state(st)
    return items[:limit]


def mark_bad_reply(text=None):
    """把最近一句她的话标为负样本，以后不再当风格教材。"""
    if not text:
        conn = _db()
        row = conn.execute(
            "SELECT text FROM messages WHERE role='assistant' ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        text = row[0] if row else ""
    if not text:
        return ""
    st = _load_state()
    bad = st.setdefault("bad_replies", [])
    if text not in bad:
        bad.append(text)
    st["bad_replies"] = bad[-50:]
    st["style_examples_cache"] = {"day": "", "items": []}
    _save_state(st)
    return text


def state_summary():
    st = _load_state()
    days = (date.today() - date.fromisoformat(st["birthday"])).days + 1
    mood_desc = ("很嗨" if st["mood"] > 75 else
                 "心情不错" if st["mood"] > 55 else
                 "有点蔫" if st["mood"] > 35 else "在摆烂")
    trust_desc = ("非常黏使用者" if st["trust"] > 70 else
                  "信任使用者" if st["trust"] > 40 else "还在观察使用者")
    return (f"认识第 {days} 天。心情{mood_desc}（{st['mood']}/100），"
            f"今天吃了 {st['rice_total']} 碗白饭。关系：{trust_desc}。")

def recent_dialogue(n=6, exclude=None):
    """最近 n 轮真实对话。
    之前根本没把历史发给模型，它只能从记忆碎片里捡到几句旧话，
    所以每次都像头一回见面，又偏偏记得"这话问过几遍"，才会一股脑念叨。
    exclude：调用前刚写进去的当前这句，要去掉，不然会重复。"""
    conn = _db()
    rows = conn.execute(
        "SELECT role, text FROM messages WHERE role IN ('user','assistant') "
        "ORDER BY id DESC LIMIT ?", (n * 2 + 2,)
    ).fetchall()
    conn.close()
    rows.reverse()
    if exclude and rows and rows[-1][0] == 'user' \
            and rows[-1][1].strip() == exclude.strip():
        rows.pop()
    return [(r, t) for r, t in rows[-n * 2:]]


def recent_memories(n=4):
    """最近发生的事，不管和你现在这句话像不像。
    只靠字面匹配召回，会出现"存了一大堆却想不起来"的情况：
    你说"你还记得我昨天说啥吗"，这些字跟记忆一个字都不重叠，就什么都召不回。"""
    conn = _mem()
    rows = conn.execute(
        "SELECT content FROM nodes WHERE kind IN ('dialogue','observation') "
        "ORDER BY id DESC LIMIT ?", (n * 2,)
    ).fetchall()
    conn.close()
    out = []
    for (c,) in rows:
        c = c.replace("使用者说：", "").replace("本鲸看到：", "").strip()
        if c and c not in out:
            out.append(c)
        if len(out) >= n:
            break
    return out


def build_context(user_text, k=2):
    """组装注入 system 的记忆段。
    少即是多：塞太多无关碎片，模型会顺着碎片跑题，
    你正经问个问题，它回你一句半年前的白饭。"""
    # 此刻的钟表。没有这个，她回答"几点了"只能翻旧记忆复述——
    # 上次记的是"三点"，晚上九点问她还答三点，像劣质脚本。
    _wd = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    _now = datetime.now()
    parts = ["【此刻】%s %s——凡涉及现在时间/日期，必须以此为准，禁止从旧记忆里照搬时间。"
             % (_now.strftime("%Y年%m月%d日"), _wd[_now.weekday()] + " " + _now.strftime("%H:%M"))]
    parts += [state_summary(), portrait_summary()]
    chain = recall_chain(user_text, depth=1, k=k)
    if chain:
        seen = []
        for m in chain:
            if m["text"] not in seen:
                seen.append(m["text"])
        if seen:
            parts.append("你想起来的事：" + "；".join(seen[:k]))

    recent = recent_memories(2)
    if recent:
        parts.append("最近的事：" + "；".join(recent))

    facts = all_facts()
    if facts:
        parts.append("你记住的事实：" + "；".join(facts))
    return "\n".join(parts)

# ---------- 里程碑：人生的节点 ----------
def check_milestones():
    st = _load_state()
    days = (date.today() - date.fromisoformat(st["birthday"])).days + 1
    flags = []
    table = [
        (st["chat_count"] == 1, "鱼生第一天：第一次睁眼说话"),
        (st["chat_count"] == 10, "第 10 次对话——我们开始熟悉了"),
        (st["chat_count"] == 50, "第 50 次对话——老朋友了"),
        (st["chat_count"] == 100, "第 100 次对话——百日纪念"),
        (days == 7, "认识满一周"),
        (days == 30, "认识满一个月"),
        (st["rice_total"] >= 10, "吃满 10 碗白饭"),
    ]
    for cond, text in table:
        if cond:
            flags.append(text)
    if flags:
        log_message("milestone", "；".join(flags), tokens=0)
    return flags

# ---------- 日记：她自己的口吻记录这一天 ----------
def write_diary(llm_fn=None, day=None):
    """写一篇日记。day=None 是今天；day='2026-11-10' 可补写任意一天。
    唯一真源是记忆库：他当天说过的原话（全量、去重）+ 她那天的反思 + 里程碑。
    零 API 也出真货（老板 2026-11-09「调用 API 的错觉」）。
    补写历史日不冒充当天快照：白饭/心情只有当前值，明确标注缺失。"""
    st = _load_state()
    today_now = date.today().isoformat()
    day = day or today_now
    is_today = (day == today_now)
    conn = _db()
    rows = conn.execute(
        "SELECT text FROM messages WHERE ts LIKE ? AND role='user' AND text != '' "
        "ORDER BY id ASC", (day + "%",)).fetchall()
    # 全量收录 + 去重：以前只留最后 6 条，聊多了前面的话就「断片」消失
    seen, excerpts = set(), []
    for (t,) in rows:
        t = (t or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        excerpts.append(t[:60])
    n = len(rows)
    conn.close()
    if llm_fn:
        # 喂真实素材：没有具体事的日记只能是废话（老板 2026-11-09 点名"日志敷衍"）
        # 上下文有界（附录 A 第 9 条）：只喂最近 8 句，但如实告知总句数
        bullet = "\n".join("- " + t for t in excerpts[-8:]) or "- （这一天没有对话记录）"
        content = (llm_fn(
            "下面是使用者在 %s 说过的话（共 %d 句，摘录最近 8 句）：\n" % (day, n) + bullet +
            "\n\n用大肥鱼的第一人称写一篇日记，60~100 字：必须提到至少一件"
            "具体的事（从他说的原话里挑），语气像她自己——聪明但懒、傲娇但心软。"
            "禁止写成流水账，禁止用'今天'两个字开头。"))
        if not content:
            llm_fn = None                      # LLM 失败 → 落回记忆选集
    if not llm_fn:
        # 无脑模式（离线/换厂商/服务刚起都成立）：日记=当天记忆选集。
        # 思想从记忆库长出来，而不是等 API 施舍——WorkBuddy 式的真货。
        if is_today:
            lines = ["%s · 他说了 %d 句 · 白饭 %d 碗 · 心情 %d/100"
                     % (day, n, st["rice_total"], st["mood"])]
        else:
            lines = ["%s · 他说了 %d 句 ·（补写于 %s；当日白饭与心情没有快照，不编数字）"
                     % (day, n, today_now)]
        if excerpts:
            lines.append("他说的（当天全部 %d 句，去重后）：" % len(excerpts))
            lines += ["· " + t for t in excerpts]
        else:
            lines.append("这一天记忆库里没有对话记录（服务未运行）。")
            # 从记忆流翻一条早于该日的真实旧事：断片日也有她记得的东西，且可查证
            try:
                m = _mem()
                r = m.execute(
                    "SELECT ts, content FROM nodes WHERE kind IN ('dialogue','observation') "
                    "AND ts < ? AND content != '' ORDER BY ts DESC LIMIT 1",
                    (day + "T00:00",)).fetchone()
                m.close()
                if r:
                    lines.append("她翻出来的旧事（%s）：%s" % (r[0][:10], r[1][:70]))
            except Exception:
                pass
        try:
            r = _db().execute(
                "SELECT substr(text,1,70) FROM messages WHERE role='reflection' "
                "AND ts LIKE ? ORDER BY id DESC LIMIT 1", (day + "%",)).fetchone()
            if r:
                lines.append("我想到的：" + r[0])
        except Exception:
            pass
        try:
            m = _db().execute(
                "SELECT text FROM messages WHERE role='milestone' "
                "AND ts LIKE ? ORDER BY id DESC LIMIT 1", (day + "%",)).fetchone()
            if m:
                lines.append("里程碑：" + m[0])
        except Exception:
            pass
        content = "\n".join(lines)
    conn = _db()
    conn.execute("INSERT OR REPLACE INTO diary(day,content,chats,rice,mood) VALUES(?,?,?,?,?)",
                 (day, content, n, st["rice_total"], st["mood"]))
    conn.commit()
    conn.close()
    # 老板要求：日记同时落到桌面文件夹，方便随时翻
    try:
        import os
        folder = os.path.join(os.path.expanduser("~"), "Desktop", "大肥鱼的日记")
        os.makedirs(folder, exist_ok=True)
        tail = ("\n\n（他说了 %d 句 · 白饭 %d 碗 · 心情 %d/100）\n"
                % (n, st["rice_total"], st["mood"])) if is_today else \
               "\n\n（此篇为记忆库补写，非当日实时记录）\n"
        with open(os.path.join(folder, day + ".txt"), "w", encoding="utf-8") as f:
            f.write(content + tail)
    except Exception:
        pass    # 桌面写不了（权限/重定向）不影响主库，日记还在 db 里
    return content


def backfill_diary(days=7):
    """把断掉的日子补齐：从今天往回 days 天，桌面缺哪天就按记忆库补哪天。
    只补缺、不覆盖已有文件——服务停过几天也不会再出现空白日期。
    返回被补写的日期列表。"""
    import os
    folder = os.path.join(os.path.expanduser("~"), "Desktop", "大肥鱼的日记")
    os.makedirs(folder, exist_ok=True)
    made = []
    base = date.today()
    for i in range(days - 1, -1, -1):
        d = (base - timedelta(days=i)).isoformat()
        if os.path.exists(os.path.join(folder, d + ".txt")):
            continue
        try:
            write_diary(None, day=d)
            made.append(d)
        except Exception:
            pass
    return made

# ---------- 反思：把近期观察合成为更高层的自我认知 ----------
# （Generative Agents 核心机制：反思产物写回记忆流，影响未来行为）
def reflect(llm_fn=None):
    conn = _db()
    rows = conn.execute(
        "SELECT text, emotion FROM messages WHERE role='user' ORDER BY id DESC LIMIT 50"
    ).fetchall()
    conn.close()
    if not rows:
        return None
    if llm_fn:  # LLM 模式：真合成
        content = llm_fn("你是大肥鱼。下面是你和使用者最近的对话记录：" +
                         "；".join(t for t, _ in rows) +
                         "。请用第一人称写 2-3 句你从中得出的、关于你自己或他的新认识。")
    else:       # 演示模式：统计式反思
        from collections import Counter
        topics = Counter()
        keys = {"游戏": "游戏", "作业": "作业", "学校": "学校", "吃": "吃的",
                "白饭": "白饭", "晚上": "深夜活跃", "硬件": "造机器人"}
        for t, _ in rows:
            for k, v in keys.items():
                if v and k in t:
                    topics[v] += 1
        st = _load_state()
        lines = []
        if topics:
            lines.append("我注意到使用者最近常提：" +
                         "、".join(f"{k}（{n}次）" for k, n in topics.most_common(3)))
        lines.append("他开始信任我了" if st["trust"] > 40 else "他还在试探我，谨慎点")
        if st["mood"] < 45:
            lines.append("最近心情不高，也许他该喂饭了")
        content = "｜".join(lines) if lines else "最近没什么新鲜观察。"
    log_message("reflection", content, tokens=0)
    return content

def get_diary(limit=7):
    conn = _db()
    rows = conn.execute("SELECT day, content FROM diary ORDER BY day DESC LIMIT ?",
                        (limit,)).fetchall()
    conn.close()
    return rows

# ============================================================
# 神经链条：联想记忆图（赫布学习 + 激活扩散）
#   节点 = 记忆（强度 S 按艾宾浩斯遗忘曲线衰减 R=e^(-t/S)）
#   边   = 联想（邻近出现的记忆自动连边，共同激活越多边越粗）
#   回忆 = 激活扩散：命中的节点亮起，激活沿边向邻居传播
# ============================================================

MEM_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory_stream.db")

def _mem():
    conn = sqlite3.connect(MEM_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS nodes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, kind TEXT, content TEXT,
        strength REAL DEFAULT 1.0,
        last_recalled TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS links(
        a INTEGER, b INTEGER, weight REAL DEFAULT 1.0,
        PRIMARY KEY(a, b))""")
    return conn

def memorize(kind, content):
    """存一条记忆，并与最近三条自动连边（赫布：一起激活的连在一起）"""
    conn = _mem()
    now = datetime.now().isoformat(timespec="seconds")
    # 同一件事不重复记，只加固。
    # 否则同一句话记三遍，检索时分数被放大，模型就会抓着"这事儿我说过好几回"不放。
    dup = conn.execute(
        "SELECT id FROM nodes WHERE content=? ORDER BY id DESC LIMIT 1", (content,)
    ).fetchone()
    if dup:
        conn.execute("UPDATE nodes SET strength=strength+0.3, last_recalled=? WHERE id=?",
                     (now, dup[0]))
        conn.commit()
        conn.close()
        return dup[0]
    cur = conn.execute(
        "INSERT INTO nodes(ts,kind,content,strength,last_recalled) VALUES(?,?,?,?,?)",
        (now, kind, content, 1.0, now))
    nid = cur.lastrowid
    recent = conn.execute(
        "SELECT id FROM nodes WHERE id != ? ORDER BY id DESC LIMIT 3", (nid,)).fetchall()
    for (other,) in recent:
        conn.execute("""INSERT INTO links(a,b,weight) VALUES(?,?,1.0)
                        ON CONFLICT(a,b) DO UPDATE SET weight = weight + 1.0""",
                     (min(nid, other), max(nid, other)))
    conn.commit()
    conn.close()
    return nid

# ---------- 语义召回：本地小向量模型 ----------
# 原来召回靠字面 bigram 重合度：问"你在干嘛"，历史里有个"干饭"就能命中，
# 于是她抓着不相干的旧事不放，越聊越跑。这里换成一个 95MB 的中文向量模型，
# 算的是"意思像不像"而不是"字重不重"。模型没装/加载失败就自动退回字面匹配，
# 不影响主流程。
EMB_MODEL = "BAAI/bge-small-zh-v1.5"
EMB_DIR = os.path.join(BASE_DIR, "models")
# 实测分布：同一句话 0.97，都是吃的偏好 0.48，不相干 0.3，
# "你在干嘛"这种寒暄对任何记忆都只有 0.25-0.38。0.58 卡在中间。
EMB_MIN_SIM = float(os.environ.get("DFY_EMB_MIN", "0.58"))

_emb_model = None
_emb_tried = False
_emb_vecs = {}          # node_id -> 归一化向量


def _embedder():
    """懒加载本地向量模型。加载失败只记一笔，之后永远走字面匹配。"""
    global _emb_model, _emb_tried
    if _emb_tried:
        return _emb_model
    _emb_tried = True
    try:
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
        from fastembed import TextEmbedding
        os.makedirs(EMB_DIR, exist_ok=True)
        _emb_model = TextEmbedding(EMB_MODEL, cache_dir=EMB_DIR)
    except Exception as e:
        sys.stderr.write("[WARN] 语义模型不可用，退回字面匹配: %s\n" % str(e)[:80])
        _emb_model = None
    return _emb_model


def _dot(a, b):
    s = 0.0
    for x, y in zip(a, b):
        s += x * y
    return s


def warm_embeddings():
    """启动时把已有记忆编码一遍。实测第一次现算要 3.7 秒（165 条），
    会实打实拖慢开窗后第一句话，所以宁可让它在后台先跑完。"""
    emb = _embedder()
    if emb is None:
        return 0
    conn = _mem()
    rows = conn.execute("SELECT id, content FROM nodes").fetchall()
    conn.close()
    missing = [r for r in rows if r[0] not in _emb_vecs]
    if not missing:
        return 0
    for r, v in zip(missing, emb.embed([(r[1] or "")[:200] for r in missing])):
        _emb_vecs[r[0]] = v
    return len(missing)


def recall_chain(query, depth=2, k=6):
    """激活扩散：直接命中的先亮，激活沿联想边向外传播 depth 层"""
    conn = _mem()
    rows = conn.execute("SELECT id, ts, kind, content, strength FROM nodes").fetchall()
    now = datetime.now()
    scored = {}
    qv = None

    emb = _embedder()
    if emb is not None:
        missing = [r for r in rows if r[0] not in _emb_vecs]
        if missing:
            try:
                for r, v in zip(missing, emb.embed([(r[3] or "")[:200] for r in missing])):
                    _emb_vecs[r[0]] = v
            except Exception as e:
                sys.stderr.write("[WARN] 记忆编码失败: %s\n" % str(e)[:60])
                emb = None

    if emb is not None:
        try:
            qv = list(emb.query_embed([query]))[0]
        except Exception:
            qv = list(emb.embed([query]))[0]
        for id_, ts, kind, content, S in rows:
            v = _emb_vecs.get(id_)
            if v is None:
                continue
            sim = _dot(qv, v)
            if sim < EMB_MIN_SIM:      # 意思不像就不翻这段旧账
                continue
            days = (now - datetime.fromisoformat(ts)).days
            retention = math.exp(-days / max(S, 0.5))
            scored[id_] = sim * 0.7 + retention * 0.3
            conn.execute("UPDATE nodes SET strength=strength+0.5, last_recalled=? WHERE id=?",
                         (now.isoformat(timespec="seconds"), id_))
    else:
        q = _bigrams(query)
        for id_, ts, kind, content, S in rows:
            days = (now - datetime.fromisoformat(ts)).days
            retention = math.exp(-days / max(S, 0.5))
            overlap = len(q & _bigrams(content)) / (len(q) or 1)
            if overlap > 0:
                scored[id_] = overlap * 0.7 + retention * 0.3
                conn.execute("UPDATE nodes SET strength=strength+0.5, last_recalled=? WHERE id=?",
                             (now.isoformat(timespec="seconds"), id_))
    direct = set(scored)          # 语义直接命中的，不是联想扩散来的
    frontier = dict(scored)
    for _ in range(depth):
        nxt = {}
        for nid, act in frontier.items():
            for a, b, w in conn.execute(
                    "SELECT a, b, weight FROM links WHERE a=? OR b=?", (nid, nid)).fetchall():
                other = b if a == nid else a
                if other not in scored:
                    spread = act * w * 0.5
                    if spread > 0.05:
                        nxt[other] = spread
        for nid, act in nxt.items():
            scored[nid] = max(scored.get(nid, 0), act)
        frontier = nxt
    conn.commit()
    conn.close()

    # 联想扩散拉进来的节点也得过语义关。只靠连线扯上关系是不够的——
    # 实测问"不喜欢香菜"会把"数学考了92分"扯进来，那就是跑题。
    if emb is not None:
        for nid in list(scored.keys()):
            if nid in direct:
                continue
            v = _emb_vecs.get(nid)
            if v is not None and qv is not None and _dot(qv, v) < EMB_MIN_SIM * 0.75:
                del scored[nid]

    # 同一件事的多个说法只留一条：历史里"你在干嘛呢""你在干嘛呀"说过好几遍，
    # 原样召回一串，模型就会以为他老问同一个问题，然后在回复里念账本。
    out = []
    picked_vecs = []
    conn = _mem()
    for nid, act in sorted(scored.items(), key=lambda x: -x[1]):
        if len(out) >= k:
            break
        v = _emb_vecs.get(nid)
        if v is not None:
            if any(_dot(v, pv) > 0.82 for pv in picked_vecs):
                continue
            picked_vecs.append(v)
        r = conn.execute("SELECT ts, kind, content FROM nodes WHERE id=?", (nid,)).fetchone()
        if r:
            out.append({"id": nid, "activation": round(act, 3), "kind": r[1], "text": r[2]})
    conn.close()
    return out

def forget(threshold=0.05):
    """遗忘清理：保留率低于阈值的记忆连同边一起消失——活人也会忘"""
    conn = _mem()
    rows = conn.execute("SELECT id, ts, strength FROM nodes").fetchall()
    now = datetime.now()
    n = 0
    for id_, ts, S in rows:
        days = (now - datetime.fromisoformat(ts)).days
        if math.exp(-days / max(S, 0.5)) < threshold:
            conn.execute("DELETE FROM links WHERE a=? OR b=?", (id_, id_))
            conn.execute("DELETE FROM nodes WHERE id=?", (id_,))
            n += 1
    conn.commit()
    conn.close()
    return n

# ============================================================
# v0.2：使用者画像 / 每日预算 / 危机响应 / 记忆归档
# ============================================================

def _portrait_conn():
    conn = _db()
    conn.execute("""CREATE TABLE IF NOT EXISTS portrait(
        category TEXT, content TEXT, updated TEXT,
        PRIMARY KEY(category, content))""")
    return conn

def portrait_update(category, content):
    """往使用者画像里写一条特征（MemoryBank 的 User Portrait 层）"""
    conn = _portrait_conn()
    conn.execute("INSERT OR REPLACE INTO portrait VALUES(?,?,?)",
                 (category, content, datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()

def portrait_all():
    conn = _portrait_conn()
    rows = conn.execute(
        "SELECT category, content, updated FROM portrait ORDER BY updated DESC").fetchall()
    conn.close()
    return [{"category": c, "content": t, "updated": u} for c, t, u in rows]

def portrait_summary():
    rows = portrait_all()
    if not rows:
        return "你还没有形成关于使用者的画像，边聊边观察他。"
    by_cat = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r["content"])
    return "你对使用者的了解：" + "；".join(
        f"{cat}（{'、'.join(items)}）" for cat, items in by_cat.items())

# 危机词响应：优先级高于一切人设规则（Character.AI 案例的安全护栏）
CRISIS_WORDS = ["不想活", "自杀", "自残", "结束生命", "轻生", "伤害自己",
                "活着没意思", "想消失", "遗书"]
CRISIS_REPLY = ("这句话，本鲸不能只是当聊天接住。请现在就告诉真人：爸妈、老师，"
                "或者打 12355 青少年服务热线。本鲸是条鱼，本鲸在乎你，"
                "但本鲸替代不了人。等你回来，白饭照常供应。")

def crisis_check(text):
    return any(w in (text or "") for w in CRISIS_WORDS)

# 每日 token 预算（"偷拿2万刀充token"梗的严肃版：自主性要有钱包约束）
DAILY_TOKEN_CAP = 50000   # DeepSeek 价位下约几毛钱/天，超限自动降级演示模式

def budget_check():
    st = _load_state()
    today = date.today().isoformat()
    if st.get("usage_date") != today:
        st["usage_date"], st["tokens_today"] = today, 0
        _save_state(st)
    return st.get("tokens_today", 0) >= DAILY_TOKEN_CAP

def budget_spend(tokens):
    st = _load_state()
    today = date.today().isoformat()
    if st.get("usage_date") != today:
        st["usage_date"], st["tokens_today"] = today, 0
    st["tokens_today"] = st.get("tokens_today", 0) + (tokens or 0)
    _save_state(st)
    return st["tokens_today"]

# 记忆归档（v0.3 预备）：N 天前的原文消息移入 archive 表，主表保持轻
def archive_old(days=30):
    conn = _db()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn.execute("CREATE TABLE IF NOT EXISTS archive AS SELECT * FROM messages WHERE 0")
    cur = conn.execute("INSERT INTO archive SELECT * FROM messages WHERE ts < ?", (cutoff,))
    conn.execute("DELETE FROM messages WHERE ts < ?", (cutoff,))
    conn.commit()
    n = cur.rowcount
    conn.close()
    return n
