@echo off
chcp 65001 >nul
cd /d "C:\Users\用户\WorkBuddy\2026-10-30-21-40-54"
echo 启动看门狗（服务死了会自动复活，窗口可最小化）...
start "" /b "C:\Users\用户\AppData\Local\Programs\Python\Python311\pythonw.exe" "大肥鱼看门狗.pyw"
timeout /t 10 /nobreak >nul
echo 完成。她的窗口马上出现；监测台在 http://127.0.0.1:8765/monitor
pause
