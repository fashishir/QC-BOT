@echo off
chcp 65001 >nul
echo.
echo ====================================================================
echo  SattAcademy Question Bank Scraper & PDF Exporter (2015-2026)
echo ====================================================================
echo.
echo What would you like to run?
echo.
echo  --- SCRAPING ACTIONS ---
echo  1. Quick Verification Scrape (5 exams only)
echo  2. Scrape ALL Board Exams + Test Papers (2015-2026)
echo  3. Scrape SSC only (2015-2026)
echo  4. Scrape HSC only (2015-2026)
echo  5. Scrape Board Exams only
echo  6. Scrape Test Papers only
echo  7. Scrape a specific year (e.g. 2024)
echo.
echo  --- PDF EXPORT ACTIONS ---
echo  8. Export ALL collected exams to PDF files
echo  9. Export SSC exams only to PDF files
echo  10. Export HSC exams only to PDF files
echo  11. Export a specific year's exams to PDF files
echo.
echo  --- VIEW & REPORTS ---
echo  12. Launch Question Bank Web Viewer (Streamlit)
echo  13. Generate CSV Summary Report only
echo.
set /p choice="Enter choice (1-13): "

if "%choice%"=="1" (
    echo Running verification test (5 exams)...
    python scraper.py --limit 5
)
if "%choice%"=="2" (
    echo Scraping ALL SSC & HSC Board Exams & Test Papers (2015-2026)...
    python scraper.py
)
if "%choice%"=="3" (
    echo Scraping SSC (2015-2026)...
    python scraper.py --class ssc
)
if "%choice%"=="4" (
    echo Scraping HSC (2015-2026)...
    python scraper.py --class hsc
)
if "%choice%"=="5" (
    echo Scraping Board Exams only...
    python scraper.py --source board
)
if "%choice%"=="6" (
    echo Scraping Test Papers only...
    python scraper.py --source test
)
if "%choice%"=="7" (
    set /p yr="Enter year (e.g. 2024): "
    echo Scraping year %yr%...
    python scraper.py --year %yr%
)
if "%choice%"=="8" (
    echo Exporting ALL collected questions to PDF files...
    python export_pdf.py
)
if "%choice%"=="9" (
    echo Exporting SSC collections to PDF files...
    python export_pdf.py --class ssc
)
if "%choice%"=="10" (
    echo Exporting HSC collections to PDF files...
    python export_pdf.py --class hsc
)
if "%choice%"=="11" (
    set /p yr="Enter year to export (e.g. 2025): "
    echo Exporting year %yr% to PDF files...
    python export_pdf.py --year %yr%
)
if "%choice%"=="12" (
    echo Launching Streamlit Viewer...
    streamlit run app.py
)
if "%choice%"=="13" (
    echo Generating CSV report...
    python scraper.py --report-only
)

echo.
pause
