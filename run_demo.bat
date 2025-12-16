@echo off
echo ==========================================
echo MARITIME RAG + ANALYTICS DEMO
echo Blurgs.ai Interview Prep
echo ==========================================

echo.
echo Step 1: Generating sample AIS data...
python -X utf8 sample_ais_data.py

echo.
echo Step 2: Running analytics demo...
python -X utf8 maritime_analytics.py

echo.
echo Step 3: Running RAG demo (requires GOOGLE_API_KEY)...
python -X utf8 maritime_rag.py

pause
