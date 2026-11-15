# -*- coding: utf-8 -*-
"""大肥鱼看门狗：电器模式的心跳。
每 15 秒体检一次服务端(8765)和页面服务(8080)，死了自动拉起。
放进启动文件夹后，开机即有鱼，无需任何操作。"""
import subprocess, time, os, sys, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable.replace('pythonw.exe', 'python.exe')
LAN = os.environ.get('DFY_LAN') == '1'
HOST = '0.0.0.0' if LAN else '127.0.0.1'
EDGE_CANDIDATES = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                   r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]

def alive(url):
    try:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        op.open(url, timeout=3)
        return True
    except Exception:
        return False

def spawn(args, cwd):
    subprocess.Popen([PY] + args, cwd=cwd,
                     creationflags=0x00000008 | 0x00000200,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     stdin=subprocess.DEVNULL)

OLLAMA = os.path.join(os.environ.get('LOCALAPPDATA', ''),
                      'Programs', 'Ollama', 'ollama.exe')

def ensure_ollama():
    """本地脑驻留：11434 没起来就拉起 ollama serve（断网兜底的常驻保障）"""
    if not os.path.exists(OLLAMA):
        return
    if not alive('http://127.0.0.1:11434/'):
        try:
            subprocess.Popen([OLLAMA, 'serve'],
                             creationflags=0x00000008 | 0x00000200,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL)
        except Exception:
            pass

def open_fish_window():
    edge = next((p for p in EDGE_CANDIDATES if os.path.exists(p)), None)
    if not edge:
        return
    import urllib.parse
    url = 'http://127.0.0.1:8080/' + urllib.parse.quote('脑袋-v0.1.html')
    subprocess.Popen([edge, '--app=' + url, '--window-size=1320,860'],
                     creationflags=0x00000008 | 0x00000200,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     stdin=subprocess.DEVNULL)

def spawn_page():
    """实体模式走白名单静态服务；普通模式仍用本机 http.server。"""
    if LAN:
        spawn(['实体页面服务.py'], BASE)
    else:
        spawn(['-m', 'http.server', '8080', '--bind', '127.0.0.1'], BASE)

def backfill_diary():
    """拉独立补写器按记忆库补齐缺失日期。服务起不来时日记也不断片。"""
    try:
        spawn(['补写日记.py'], BASE)
    except Exception:
        pass

# 开机先确保服务起来，再开她的窗口
if not alive('http://127.0.0.1:8765/health'):
    spawn(['-m', 'uvicorn', 'server:app', '--host', HOST, '--port', '8765'],
          os.path.join(BASE, '大肥鱼服务端'))
if not alive('http://127.0.0.1:8080/'):
    spawn_page()
backfill_diary()          # 与服务解耦：一开机先把断掉的日期补上
time.sleep(8)
open_fish_window()

_last_backfill_day = None
while True:
    time.sleep(15)
    # 每天一次补写：跨零点、服务重启、停电都不会留下空白日期
    _today = time.strftime('%Y-%m-%d')
    if _today != _last_backfill_day:
        _last_backfill_day = _today
        backfill_diary()
    if not alive('http://127.0.0.1:8765/health'):
        try:
            spawn(['-m', 'uvicorn', 'server:app', '--host', HOST, '--port', '8765'],
                  os.path.join(BASE, '大肥鱼服务端'))
        except Exception:
            pass
    if not alive('http://127.0.0.1:8080/'):
        try:
            spawn_page()
        except Exception:
            pass
    ensure_ollama()
