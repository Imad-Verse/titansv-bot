@echo off
setlocal EnableDelayedExpansion
title TitanSv Bot Manager
color 0B

:menu
cls
echo ========================================================
echo                 TITAN SV BOT MANAGER
echo ========================================================
echo.
echo    [1] Start Bot (Build ^& Run)
echo    [2] Stop Bot
echo    [3] View Bot Logs
echo    [4] Log Out from Telegram Cloud (Run once!)
echo    [5] Restart Bot
echo    [6] Exit
echo.
echo ========================================================
set /p choice="Select an option (1-6): "

if "%choice%"=="1" goto start_bot
if "%choice%"=="2" goto stop_bot
if "%choice%"=="3" goto view_logs
if "%choice%"=="4" goto logout_cloud
if "%choice%"=="5" goto restart_bot
if "%choice%"=="6" goto eof

echo Invalid choice. Try again.
timeout /t 2 >nul
goto menu

:start_bot
cls
echo Starting TitanSv Bot and Local Telegram API Server...
echo This might take a minute on the first run.
docker compose up -d --build
echo.
echo Bot is now running in the background!
pause
goto menu

:stop_bot
cls
echo Stopping TitanSv Bot...
docker compose down
echo.
echo Bot stopped successfully.
pause
goto menu

:view_logs
cls
echo Showing Live Logs (Press Ctrl+C to stop viewing)...
docker compose logs -f bot
pause
goto menu

:logout_cloud
cls
echo ========================================================
echo WARNING: This will log your bot out from the Telegram 
echo Cloud Server. This is required ONLY ONCE when switching 
echo to the Local API Server.
echo ========================================================
echo.
set /p confirm="Are you sure you want to proceed? (Y/N): "
if /I "%confirm%" NEQ "Y" goto menu

echo Logging out...
python -c "import telebot; import os; from dotenv import load_dotenv; load_dotenv(); bot = telebot.TeleBot(os.getenv('TELEGRAM_BOT_TOKEN')); print('Result:', bot.log_out())"
echo.
echo Log out command sent. 
echo Note: If it says 'True', it succeeded. If it gives an error, it might already be logged out.
pause
goto menu

:restart_bot
cls
echo Restarting TitanSv Bot...
docker compose restart
echo.
echo Bot restarted successfully.
pause
goto menu

:eof
exit
