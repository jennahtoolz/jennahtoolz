@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
if exist ".venv\Scripts\python.exe" goto installed
where py >nul 2>nul
if errorlevel 1 goto use_python
py -3 setup.py
if errorlevel 1 goto failed
goto installed
:use_python
python setup.py
if errorlevel 1 goto failed
:installed
if not exist ".env" copy /y ".env.example" ".env" >nul
".venv\Scripts\python.exe" run_bot.py --smoke-test
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -c "import os,sys; from dotenv import load_dotenv; load_dotenv(); sys.exit(0 if os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY') else 2)"
if not errorlevel 1 goto profile
echo Enter your Gemini API key in .env, save the file, and close Notepad.
start /wait "" notepad.exe ".env"
".venv\Scripts\python.exe" -c "import os,sys; from dotenv import load_dotenv; load_dotenv(); sys.exit(0 if os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY') else 2)"
if errorlevel 1 goto failed
:profile
if exist "persona.json" goto login
copy /y "persona.example.json" "persona.json" >nul
echo Add only your own profile facts inside about_you. Save the JSON and close Notepad.
start /wait "" notepad.exe "persona.json"
:login
if exist "auth.json" goto run
".venv\Scripts\python.exe" save_auth.py
if errorlevel 1 goto failed
:run
".venv\Scripts\python.exe" run_bot.py --implementation playwright
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo SurveyBot stopped. Read the message above; no success is being assumed.
pause
exit /b 1
