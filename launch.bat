    @echo off
cd /d "%~dp0"
python -m streamlit run app.py --browser.gatherUsageStats false
pause
