@echo off
chcp 65001 >nul
title 远程助手 - 不要关闭此窗口
echo ================================================
echo   正在启动远程助手，请勿关闭此窗口
echo   日志会同时写入 agent.log
echo ================================================
echo.
agent.exe pc1
echo.
echo [已退出] 按任意键关闭
pause >nul
