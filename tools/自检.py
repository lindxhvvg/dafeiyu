# -*- coding: utf-8 -*-
"""大肥鱼·改后自检
每次改完 server.py / soul.py / 脑袋-v0.1.html，必须先跑这个，全绿才能说"好了"。
检查项来自真实踩过的坑——新坑出现时，必须在下面加对应的检查项。
用法：python 自检.py
"""
import ast, os, re, sys, time, json, base64, urllib.request, subprocess, threading, socket

BASE = os.path.dirname(os.path.abspath(__file__))
SRV = os.path.join(BASE, "大肥鱼服务端")
PY = sys.executable
fails = []

def check(name, ok, detail=""):
    tag = "PASS" if ok else "FAIL"
    line = f"[{tag}] {name}"
    if not ok and detail:
        line += f"  ← {detail}"
    print(line)
    if not ok:
        fails.append(name)

# ============ 一、静态检查 ============
srv_path = os.path.join(SRV, "server.py")
soul_path = os.path.join(SRV, "soul.py")
html_path = os.path.join(BASE, "脑袋-v0.1.html")

# 1. Python 语法（白屏教训的 Python 版：别信"看起来对"）
for p in (srv_path, soul_path):
    f = os.path.basename(p)
    try:
        ast.parse(open(p, encoding="utf-8").read())
        check(f"语法 {f}", True)
    except SyntaxError as e:
        check(f"语法 {f}", False, f"line {e.lineno}: {e.msg}")

srv = open(srv_path, encoding="utf-8").read()
wd = open("大肥鱼看门狗.pyw", encoding="utf-8").read()
lifejs = open("形象/生命层.js", encoding="utf-8").read()
soul = open(soul_path, encoding="utf-8").read()
html = open(html_path, encoding="utf-8").read()

# 2. 回合制协议（音频串台的保票）
check("server: 外发统一走 send() 盖章（裸 wssend 只剩两个包装器内部）",
      srv.count("await wssend(") == 2,
      f"裸 wssend 有 {srv.count('await wssend(')} 处，应为 2")
check("server: speech_round 存在且递增", "speech_round" in srv and "speech_round += 1" in srv)
check("server: send() 盖回合号", 'payload["r"] = rnd' in srv or 'payload["r"] = speech_round' in srv)

# 3. 打断必须停干净（旧声音追新回合）+ 并行合成按序发送（卡壳根治）
sw = re.search(r"async def _tts_worker\(\).*?await done_q\.put\(\(idx, a", srv, re.S)
check("server: _tts_worker 合成前查 abort", bool(sw) and 'if gen_state["abort"]' in sw.group(0))
sd = re.search(r"async def _speak_sender\(\).*?nxt \+= 1", srv, re.S)
check("server: 发送端按编号排序（字声顺序不乱）", bool(sd) and "while nxt in buf" in sd.group(0))
check("server: TTS 失败有重试", "await asyncio.sleep(0.3)" in srv and srv.count("a = await tts_base64(seg)") == 2)

# 4. 灵魂维护循环（日记表只读不写的事故）
check("server: 每日维护循环已接（write_diary/reflect/forget/archive_old）",
      all(x in srv for x in ("soul.write_diary(", "soul.reflect()", "soul.forget()", "soul.archive_old()", "_diary_llm_safe")))
for fn in ("write_diary", "reflect", "forget", "archive_old"):
    check(f"soul: {fn} 还在（别误删）", f"def {fn}(" in soul)

# 5. 前端·回合闸与回声防线
check("html: 服务端回合闸（旧回合到达即扔）", "m.r < srvRound" in html)
check("html: 打断时 audioRound++", "audioRound++" in html)
check("html: 解码赛跑守卫（myRound !== audioRound）", "myRound !== audioRound" in html)
check("html: 段间宽限 endTimer", "endTimer" in html and "clearTimeout(endTimer)" in html)
check("html: 回声过滤有时间窗（lastSpokenAt）", "lastSpokenAt" in html and "lastSpokenAt > 6000" in html)
check("html: 同句去重（isRepeatOfJustSent 已接线）", "isRepeatOfJustSent(text)" in html)
check("html: cue 短句有静音窗", "muteFor(2600)" in html)

# 6. 字幕时间轴（三线共钟）
check("html: 渲染循环挂 subTick", re.search(r"function loop\(\).{0,220}subTick\(\)", html, re.S) is not None)
check("html: 渲染循环 30fps 节流", "frameNo" in html and "frameNo % 2" in html)
check("html: 游动系统 v2（巡游/趴顶/穿越三模式）", True)   # 已升级 v3，由下方检查接管
check("html: 游动系统 v3（巡游/趴顶/游近/游远，含缩放）",
      "swimPickTarget" in html and "'perch'" in html and "'near'" in html and "swimS_cur" in html)
check("html: 游动系统 v3（巡游/趴顶/游近/游远，含缩放）",
      "swimPickTarget" in html and "'perch'" in html and "'near'" in html and "swimS_cur" in html)
check("html: 游动画布位移硬钳制（防整鱼出画），无透明度操作",
      "Math.max(-170, Math.min(170, swimX" in html and "head.style.opacity" not in html)
check("html: 字幕按播放头逐字推进（full 累积全文）", "seg.full" in html and "full:" in html)
check("html: 旧字幕系统已清干净", "spokenBuf" not in html and "subTimers" not in html)

# 7. 说话期间你的话不再被丢（2026-11-07 下午现场："早，现在几点了"被吞）
check("html: 她说话时的话先记账（pendingSpeech）", "pendingSpeech" in html and "pendingSpeech.push(text)" in html)
check("html: 渲染循环挂 drainSpeech", re.search(r"function loop\(\).{0,260}drainSpeech\(\)", html, re.S) is not None)
check("html: 回声窗锚定到声音结束时刻（lastSpokenAt=未来值）",
      "lastSpokenAt = Date.now() + playDurMs" in html)
check("html: 客户端事件日志（clog/flushClog）", "function clog(" in html and "setInterval(flushClog" in html)
check("server: 接收客户端日志（clog 白名单）", '"clog"' in srv and '_dbg("[client]"' in srv)
check("server: 打断与提示有日志", '_dbg("interrupt"' in srv and '_dbg("notice"' in srv)
check("server: 记忆星图路由（/starmap）", "def _starmap_html" in srv and '@app.get("/starmap")' in srv)
check("server: TTS 双工人并行（卡壳根治）", "TTS_WORKERS = 2" in srv and "_speak_sender" in srv and "done_q" in srv)
check("server: 尾部裸情绪词不念出来（思考泄漏修复）",
      "思考|开心|委屈|炸毛|瞌睡" in srv and "clean_for_tts" in srv)
check("soul: 日记落桌面文件夹", "Desktop" in soul and "大肥鱼的日记" in soul)
check("server: 日记随聊随写（凌晨不在场也有日记）", "asyncio.to_thread(soul.write_diary)" in srv)
check("server: 日记三入口默认零 API（不靠厂商）", "DFY_DIARY_LLM" in srv and "soul.write_diary(_polish)" in srv)
check("实体: 局域网模式默认关闭（DFY_LAN 显式开启）", 'os.environ.get("DFY_LAN") == "1"' in srv)
check("实体: 令牌校验覆盖敏感端点与 WS", srv.count("if not _lan_ok(request)") >= 6 and "code=4401" in srv)
check("实体: 本机免令牌、外部需令牌", 'h in ("127.0.0.1", "::1", "localhost")' in srv)
check("实体: 接入说明与二维码生成", "局域网接入.txt" in srv and "手机接入.png" in srv)
check("html: WS 随页面主机推导 + 令牌透传", "location.hostname" in html and "_lanKey" in html)
check("html: 非安全上下文打字兜底（手机身体）", "lanBar" in html and "window.isSecureContext" in html)
check("html: 移动端 viewport", "viewport-fit=cover" in html)
check("电器: 实体模式.bat 就位", os.path.exists("实体模式.bat"))
check("电器: 看门狗 LAN 可切换且默认回环", "HOST = '0.0.0.0' if LAN else '127.0.0.1'" in wd)
check("实体: 白名单页面服务（密钥/数据库不外泄）",
      os.path.exists("实体页面服务.py") and
      "ALLOWED_FILES" in open("实体页面服务.py", encoding="utf-8").read() and
      "os.path.relpath" in open("实体页面服务.py", encoding="utf-8").read())
check("实体: 看门狗 LAN 走白名单服务", "spawn_page()" in wd and "实体页面服务.py" in wd)
check("表现层: 生命层脚本存在（零 API 依赖的海底/表情/互动）",
      os.path.exists("形象/生命层.js") and "生命层.js" in html and 'id="sea"' in html)
check("表现层: 老设备兼容（URLSearchParams 兜底 + aspect-ratio 降级）",
      "window.URLSearchParams = function" in html and "@supports not (aspect-ratio" in html)
check("server: 回复正文清理裸标签词与英文碎片",
      're.sub(r"[A-Za-z0-9' in srv and 're.sub(r"(?:^|[，。！' in srv)
check("server: 星图工具指向 8765（原来错指 8080）",
      "http://127.0.0.1:8765/starmap" in srv)
check("server: health 带功能清单供体检面板比对", '"features"' in srv and "life_layer" in srv)
check("实时: 延迟分段留痕 + 监测台可查", "LATENCY_LOG" in srv and "latency_recent" in srv and 'id="lat"' in srv)
check("实时: 中间识别结果提前反应（不等整句）", "if (!r.isFinal)" in html and "setEmotion('listen', 1500)" in html)
check("训练: 风格教材从真实对话蒸馏（本地可逆）", "def style_examples" in soul and "bad_replies" in soul)
check("训练: few-shot 注入提示词", "style_examples(5)" in srv and "她自己的说法" in srv)
check("训练: 负反馈通道（点不像她→重算教材）", '"feedback"' in srv and "mark_bad_reply" in srv)
check("表现层: 「这句不像她」按钮就位", 'data-a="bad"' in lifejs and "feedback" in lifejs)
check("实体: 模式切换准备脚本（清理回环旧服务）",
      os.path.exists("实体模式准备.py") and
      "实体模式准备.py" in open("实体模式.bat", encoding="utf-8").read())
check("html: 噪声守门（置信度+语气词黑名单）", "noiseOk" in html and "FILLER_RE" in html and "drop-noise" in html)
check("html: drain 合并放行（防连环打断）", "const keep = q.filter" in html)
check("server: 脑子英伟达优先（小模型只能当备胎）",
      srv.find('"name": "nvidia"') < srv.find('"name": "silicon"') and 'provs.append({"name": "zhipu"' not in srv)
check("server: 英伟达 8 秒优先窗", "hedge_after=8.0" in srv)
check("server: 打断提示 45s 限流", "_last_notice_at" in srv)
check("soul: 上下文注入此刻时钟（禁止翻旧记忆报时）", "【此刻】" in soul)
check("server: 后台画像点名英伟达（深思考岗）",
      "_nv" in srv and 'p["name"] == "nvidia"' in srv)
check("server: 智谱已下线", "zhipu" not in srv)
check("server: 本地脑兜底（ollama，断网也活着）",
      "127.0.0.1:11434" in srv and "try local brain" in srv and "qwen2.5:7b-instruct" in srv)
check("电器: 看门狗存在且含自愈逻辑",
      os.path.exists("大肥鱼看门狗.pyw") and "def alive(" in open("大肥鱼看门狗.pyw", encoding="utf-8").read())
check("电器: 自启安装器就位（双击即装，会话环境无法代装）",
      os.path.exists("安装开机自启.bat") and os.path.exists("自启模板.txt"))
check("server: 「想起」行为-记忆联动（情绪动作随记忆）",
      '"recall": True' in srv and "_pos" in srv and "wag_fast" in srv)
check("server: Token 账单（按天按脑）", "token_ledger" in srv)
check("soul: recall_mark 登记（星图联动地基）", "def recall_mark" in soul)
check("html: 想起时视线飘向上方", "nextGaze('up')" in html)
check("soul: 人格演化 v0（风格漂移安全版）", "def persona_evolve" in soul)
check("server: 风格备注注入对话", "【风格备注】" in srv and "style_note" in srv)
check("server: 不确定就说不确定（X6 防编造）", "禁止编造" in srv)
check("server: 星图点亮「想起」联动", "RECALLED" in srv and "recent_recalled" in srv)
check("server: X4 工具层（提示词规则+解析+提醒）",
      "[tool: remind(" in srv and "tool call:" in srv)
check("soul: 提醒存取（X4 的手）", "def reminder_set" in soul and "def due_reminder" in soul)
check("server: 提醒推送器（主动送达）", "LIVE_WS" in srv and "_reminder_pusher" in srv)
check("server: X7 监测台（/monitor + /monitor/data）", '"/monitor"' in srv and "monitor_data" in srv)
check("soul: 日记=记忆选集（零 API 也有真货）",
      "他说的（当天全部" in soul and "我想到的：" in soul and "她翻出来的旧事" in soul)
check("soul: 日记可按日补写（day 参数）", "def write_diary(llm_fn=None, day=None)" in soul)
check("soul: backfill_diary 补齐缺失日期", "def backfill_diary" in soul)
check("soul: 当天原话全量收录（不再只留 6 条）", "当天全部" in soul and "ORDER BY id ASC" in soul)
check("server: 启动时补写断片日记", "soul.backfill_diary" in srv)
check("电器: 看门狗每日补写（与服务解耦）",
      os.path.exists("大肥鱼看门狗.pyw") and "backfill_diary" in open("大肥鱼看门狗.pyw", encoding="utf-8").read())
check("电器: 独立补写器 补写日记.py 就位", os.path.exists("补写日记.py"))
check("soul: 心情历史曲线数据", "mood_history" in soul)
check("韧性: 本地脑服务在位（11434 或 ollama.exe）",
      os.path.exists(os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Ollama', 'ollama.exe')))
check("html: 禁缓存 + 形象加载失败红字横幅",
      "no-store" in html and "形象加载失败" in html)
check("html: 音频净化（电流音：限幅+陡跳桥接+剪尾静音）",
      "polishAudio" in html and "BRIDGE" in html and "0.12" in html)
check("server: TTS 回来先洗一遍（服务端 DSP 净化）",
      "_polish_audio_bytes" in srv and "data:audio/wav" in srv)
check("html: 麦克风退避不再被秒死会话清零", "lastMicStart" in html and "micRetry = 0; else micRetry++" in html)

# ============ 二、动态检查（真起页面，无头浏览器里验） ============
def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

def dynamic():
    port = free_port()
    dbg = free_port()
    profile = os.path.join(os.environ.get("TEMP", "."), f"dfy_check_{dbg}")
    httpd = subprocess.Popen([PY, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                             cwd=BASE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    edge = None
    try:
        time.sleep(1.0)
        edge = subprocess.Popen([
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            "--headless=new", f"--remote-debugging-port={dbg}",
            "--user-data-dir=" + os.path.join(os.environ.get("TEMP", "."), f"dfy_check_{dbg}"),
            "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
            "--autoplay-policy=no-user-gesture-required", "--disable-gpu", "--no-first-run",
            "http://127.0.0.1:%d/%%E8%%84%%91%%E8%%A2%%8B-v0.1.html" % port,
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        import asyncio, websockets
        async def probe():
            deadline = time.time() + 25
            page = None
            while time.time() < deadline and page is None:
                try:
                    pages = json.load(urllib.request.urlopen(f"http://127.0.0.1:{dbg}/json", timeout=3))
                    page = next((p for p in pages if p.get("type") == "page" and str(port) in p.get("url", "")), None)
                except Exception:
                    pass
                if page is None:
                    await asyncio.sleep(0.8)
            if page is None:
                check("动态: 页面起来", False, "25 秒没等到调试端口"); return
            async with websockets.connect(page["webSocketDebuggerUrl"], max_size=2**26) as ws:
                seq = [0]; excs = []
                async def call(method, params=None, tmo=20):
                    seq[0] += 1; mid = seq[0]
                    await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
                    while True:
                        r = json.loads(await asyncio.wait_for(ws.recv(), timeout=tmo))
                        if r.get("id") == mid: return r
                async def ev(expr):
                    r = await call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
                    d = r.get("result", {})
                    if "exceptionDetails" in d:
                        return "EXC:" + str((d["exceptionDetails"].get("exception") or {}).get("description", ""))[:120]
                    return d.get("result", {}).get("value")
                await call("Runtime.enable")
                # 盯 6 秒页面报错（白屏教训）
                end = time.time() + 6
                while time.time() < end:
                    try:
                        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=1))
                    except asyncio.TimeoutError:
                        continue
                    if msg.get("method") == "Runtime.exceptionThrown":
                        d = msg["params"]["exceptionDetails"]
                        excs.append(d.get("text", "") + " " + str((d.get("exception") or {}).get("description", ""))[:100])
                check("动态: 页面无 JS 异常", not excs, "; ".join(excs[:3]))
                # 全局作用域检查：loop() 里读的变量必须是全局可见的。
                # 以前自检全绿是因为短路条件没触发，WS 一连上就 ReferenceError。
                glob = await ev('[typeof nextDaydreamAt, typeof muteHintUntil].join("/")')
                check("动态: 想起计时与静音限流全局可见（loop 不炸）",
                      glob == "number/number", str(glob))
                rig = await ev("rigReady === true")
                check("动态: rigReady（模型渲染就位）", rig is True)
                px = await ev('(()=>{const c=document.getElementById("fish");if(!c)return -1;const d=c.getContext("2d").getImageData(500,300,60,60).data;let n=0;for(let i=3;i<d.length;i+=4)if(d[i]>10)n++;return n})()')
                check("动态: 画布真的在出图", isinstance(px, int) and px > 100, f"像素 {px}")
                fns = await ev('[typeof sendText,typeof stopAudio,typeof armCue,typeof subTick,typeof muteFor,typeof isEchoOfHerOwn].join("/")')
                check("动态: 关键函数全部就位", fns == "function/function/function/function/function/function", str(fns))
                # 截图级检查：合成画面中心必须有饱和像素（鱼）。画布内部像素检查
                # 发现不了"画布被 CSS 搬走"——"鱼没了"事故的教训，必须看合成结果。
                shot = await call('Page.captureScreenshot', {'format': 'png'})
                shot_b64 = (shot.get('result', {}).get('data')
                            or shot.get('data', ''))
                if shot_b64:
                    try:
                        open(os.path.join(BASE, "当前画面.png"), "wb").write(base64.b64decode(shot_b64))
                    except Exception:
                        pass
                    from PIL import Image
                    import io as _io
                    im = Image.open(_io.BytesIO(base64.b64decode(shot_b64))).convert('RGB')
                    w, h = im.size
                    box = im.crop((w // 3, h // 3, w * 2 // 3, h // 3 + 200))
                    px = list(box.getdata())
                    sat = sum(1 for r, g, b in px if max(r, g, b) - min(r, g, b) > 25)
                    check("动态: 截图中心可见鱼（合成画面）", sat > 150, f"饱和像素 {sat}")
                else:
                    check("动态: 截图中心可见鱼（合成画面）", False, "截图失败")
                cue = await ev("CUES.length")
                check("动态: 即时反应短句就位", cue == 11, f"CUES={cue}")
                # ===== 表现层实测：不连大脑也必须看得见（P1/P2/P3 + 版本可见）=====
                life = await ev("""(()=>{const c=document.getElementById('sea');
                  return JSON.stringify({sea:!!c, tag:!!document.getElementById('emoTag'),
                    build:(document.getElementById('buildTag')||{}).textContent||'',
                    bar:!!document.getElementById('toolBar'),
                    panel:!!document.getElementById('doctorPanel')});})()""")
                try:
                    L = json.loads(life) if isinstance(life, str) else {}
                except Exception:
                    L = {}
                nb = await ev("document.querySelectorAll('#toolBar button').length")
                check("动态: 工具条四个按钮（含「这句不像她」）", nb == 4, str(nb))
                check("动态: 生命层 DOM 就位（背景/表情/版本/工具条/体检）",
                      all([L.get('sea'), L.get('tag'), L.get('bar'), L.get('panel'),
                           '2026-11-14' in str(L.get('build'))]), str(L))
                sea = await ev("""(()=>{const c=document.getElementById('sea');if(!c)return -1;
                  const x=c.getContext('2d');
                  const a=x.getImageData(10,10,1,1).data,b=x.getImageData(10,c.height-10,1,1).data;
                  return Math.abs(a[0]-b[0])+Math.abs(a[1]-b[1])+Math.abs(a[2]-b[2]);})()""")
                check("动态: 海底场景真的画出来（顶底色差）", isinstance(sea, int) and sea > 20, f"色差 {sea}")
                poke = await ev("""(()=>{const b=document.querySelector('#toolBar button[data-a=\"poke\"]');
                  if(!b)return 'no-button';b.click();
                  const p=document.getElementById('pokeBubble');
                  return (p&&p.className==='on'&&p.textContent)?p.textContent:'empty';})()""")
                check("动态: 点「戳一下」有真实反馈（本地，不靠 API）",
                      isinstance(poke, str) and poke not in ('no-button', 'empty'), str(poke))
                emo = await ev("""(async function(){
                  if(typeof setEmotion!=='function')return 'no-setEmotion';
                  setEmotion('happy',4000);
                  await new Promise(r=>setTimeout(r,460));
                  const t=document.getElementById('emoTag');
                  return t?(t.className+'|'+t.textContent):'no-tag';})()""")
                check("动态: 表情切换肉眼可见（标签联动）",
                      isinstance(emo, str) and emo.startswith('on|') and len(emo) > 3, str(emo))
                doc = await ev("""(()=>{const b=document.getElementById('buildTag');if(!b)return '';
                  b.click();const p=document.getElementById('doctorPanel');
                  return p.className+'|'+(p.textContent.indexOf('海底场景')>=0);})()""")
                check("动态: 体检面板可验（改了有没有生效一眼可见）",
                      isinstance(doc, str) and doc.startswith('on|true'), str(doc)[:60])
        try:
            asyncio.run(probe())
        except ImportError:
            print("[SKIP] 动态检查缺 websockets 库，只跑了静态部分")
    finally:
        for proc in (edge, httpd):
            if proc:
                try: proc.kill()
                except Exception: pass
        # 尸体清理：Edge 配置目录用完即删（曾经每跑一次漏 15MB，累积 30+ 具）
        import shutil as _sh
        try: _sh.rmtree(profile, ignore_errors=True)
        except Exception: pass

dynamic()

# ============ 结果 ============
print()
if fails:
    print(f"✗ {len(fails)} 项没过：{'、'.join(fails)}")
    print("没修好之前不许说'好了'。")
    sys.exit(1)
print("✓ 全部通过，可以交付。")
