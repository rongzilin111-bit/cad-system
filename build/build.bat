@echo off
REM PyInstaller 打包脚本（Windows）
REM 用法：在 dimension-reconstruct 根目录运行 build\build.bat

cd /d "%~dp0.."
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
pyinstaller build\app.spec
echo.
echo 打包完成：dist\dimension-reconstruct\
pause
