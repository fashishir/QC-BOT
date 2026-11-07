@echo off
chcp 65001 >nul
echo.
echo ====================================================================
echo  Job Exam MCQ Question Bank 2025-2026
echo ====================================================================
echo.
echo  1. Scrape SattAcademy job categories (all 40, page 1 only)
echo  2. Import approved Live MCQ full sets
echo  3. Publish job_archive.db
echo  4. Launch Streamlit app
echo  5. Generate coverage report
echo  6. Export PDFs with answers
echo  7. Export CSV with answers
echo  8. Full pipeline (scrape + Live MCQ + publish)
echo  9. Quick verification scrape (5 exams)
echo.
set /p choice="Enter choice (1-9): "

if "%choice%"=="1" (
    python -m job_scraper scrape
)
if "%choice%"=="2" (
    python -m job_scraper import-livemcq
)
if "%choice%"=="3" (
    python sync_db.py
)
if "%choice%"=="4" (
    streamlit run app.py
)
if "%choice%"=="5" (
    python -m job_scraper report
)
if "%choice%"=="6" (
    python export_pdf.py --with-answers
)
if "%choice%"=="7" (
    python export_pdf.py --with-answers --csv pdf_exports/questions.csv
)
if "%choice%"=="8" (
    python -m job_scraper scrape
    python -m job_scraper import-livemcq
    python sync_db.py
)
if "%choice%"=="9" (
    python -m job_scraper scrape --limit-exams 5
)

echo.
pause
