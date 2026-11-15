# -*- coding: utf-8 -*-
"""本地脑安装器：下载 ollama → 静默安装 → 拉取 qwen2.5:7b-instruct 模型。
全程写日志到 %TEMP%\\本地脑安装.log，支持中断后重跑（模型下载断点续传）。"""
import urllib.request, subprocess, os, sys, time

LOG = os.path.join(os.environ.get('TEMP', '.'), '本地脑安装.log')
SETUP = os.path.join(os.environ.get('TEMP', '.'), 'OllamaSetup.exe')

def log(msg):
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(time.strftime('[%H:%M:%S] ') + str(msg) + '\n')

def download(url, dst):
    if os.path.exists(dst) and os.path.getsize(dst) > 100 * 1024 * 1024:
        log('安装包已存在，跳过下载')
        return
    log('开始下载 ' + url)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60) as r, open(dst, 'wb') as f:
        total = int(r.headers.get('Content-Length', 0) or 0)
        done = 0
        while True:
            chunk = r.read(1024 * 512)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total and done % (20 * 1024 * 1024) < 512 * 1024:
                log('下载进度 %d/%d MB' % (done // 1048576, total // 1048576))
    log('下载完成: %d 字节' % os.path.getsize(dst))

def main():
    try:
        log('=== 本地脑安装开始 ===')
        download('https://ollama.com/download/OllamaSetup.exe', SETUP)
        log('静默安装中（约 1 分钟）...')
        subprocess.run([SETUP, '/VERYSILENT', '/NORESTART'], check=True, timeout=300)
        time.sleep(8)
        ollama = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Ollama', 'ollama.exe')
        if not os.path.exists(ollama):
            ollama = r'C:\Program Files\Ollama\ollama.exe'
        assert os.path.exists(ollama), '安装后找不到 ollama.exe'
        log('ollama 就位: ' + ollama)
        # 拉模型（4.7GB，断点续传，中断重跑即续传）
        log('开始拉取模型 qwen2.5:7b-instruct（约 4.7GB）...')
        r = subprocess.run([ollama, 'pull', 'qwen2.5:7b-instruct'], timeout=7200,
                           capture_output=True, text=True)
        log('模型拉取退出码 %d' % r.returncode)
        if r.returncode == 0:
            lst = subprocess.run([ollama, 'list'], capture_output=True, text=True)
            log('已安装模型:\n' + lst.stdout)
            log('=== 本地脑安装完成 ===')
        else:
            log('=== 拉取失败，重跑本脚本即续传 ===')
    except Exception as e:
        log('=== 安装异常: %s ===' % str(e)[:200])

if __name__ == '__main__':
    main()
