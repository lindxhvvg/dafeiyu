# -*- coding: utf-8 -*-
"""切换到实体模式前，清掉仍绑在回环地址的旧服务。

看门狗的存活检查会跳过重启，所以普通模式残留的 8765 / 8080 / 看门狗
必须先停掉，新进程才会按 0.0.0.0 监听。只处理本项目进程。
"""
import os
import psutil

ME = os.getpid()
killed = []
for p in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        if p.info['pid'] == ME:
            continue
        cl = ' '.join(p.info['cmdline'] or [])
        name = (p.info['name'] or '').lower()
        if 'python' not in name:
            continue
        if ('-m uvicorn server:app' in cl
                or '-m http.server 8080' in cl
                or '实体页面服务.py' in cl
                or '大肥鱼看门狗.pyw' in cl) and '-c' not in cl:
            p.kill()
            killed.append(p.info['pid'])
    except Exception:
        pass
print('已清理旧服务进程:', killed if killed else '无')
