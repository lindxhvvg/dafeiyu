@echo off
chcp 65001 >nul
cd /d "C:\Users\用户\WorkBuddy\2026-10-30-21-40-54"
echo 实体模式（阶段 1）：让手机或平板当她的身体
echo 前提：手机与这台电脑连同一个 WiFi。
echo.
echo 正在切换服务绑定（会重启一次她的服务）...
"C:\Users\用户\AppData\Local\Programs\Python\Python311\python.exe" "实体模式准备.py"
set DFY_LAN=1
start "" /b "C:\Users\用户\AppData\Local\Programs\Python\Python311\pythonw.exe" "大肥鱼看门狗.pyw"
timeout /t 12 /nobreak >nul
if exist "局域网接入.txt" (
  echo 接入地址已生成：局域网接入.txt
  echo 同目录的 手机接入.png 可以用手机扫码。
  start "" notepad "局域网接入.txt"
) else (
  echo 接入文件没有生成，请检查服务端是否启动成功。
)
echo.
echo 关闭这个窗口不会关掉她；想退回纯本机模式，请重新双击 启动大肥鱼.bat。
pause
