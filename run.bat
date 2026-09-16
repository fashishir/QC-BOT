@echo off
chcp 65001 >nul
echo.
echo =========================================
echo  Bangladesh Board Question Scraper
echo =========================================
echo.
echo What do you want to do?
echo.
echo  1. TRIAL RUN (first 5 exams only - test)
echo  2. SCRAPE ALL  (all boards, all years)
echo  3. SCRAPE SSC only
echo  4. SCRAPE HSC only
echo  5. SCRAPE one specific year (enter year)
echo  6. Open the Viewer UI (Streamlit)
echo  7. Generate CSV report only
echo.
set /p choice="Enter choice (1-7): "

if "%choice%"=="1" (
    echo Running trial (5 exams)...
    .venv\Scripts\python.exe scraper.py --limit 5
)
if "%choice%"=="2" (
    echo Scraping ALL questions... (this takes a long time)
    .venv\Scripts\python.exe scraper.py
)
if "%choice%"=="3" (
    echo Scraping SSC questions...
    .venv\Scripts\python.exe scraper.py --class ssc
)
if "%choice%"=="4" (
    echo Scraping HSC questions...
    .venv\Scripts\python.exe scraper.py --class hsc
)
if "%choice%"=="5" (
    set /p year="Enter year (e.g. 2024): "
    echo Scraping year %year%...
    .venv\Scripts\python.exe scraper.py --year %year%
)
if "%choice%"=="6" (
    echo Opening Streamlit UI...
    .venv\Scripts\streamlit.exe run app.py
)
if "%choice%"=="7" (
    .venv\Scripts\python.exe scraper.py --report-only
)

echo.
pause
