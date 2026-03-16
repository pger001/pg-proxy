@echo off
echo 运行API诊断...
python diagnose_api.py > api_diagnose_result.txt 2>&1
echo 诊断完成，结果已保存到 api_diagnose_result.txt
type api_diagnose_result.txt
pause
