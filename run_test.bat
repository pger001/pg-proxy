@echo off
python quick_test.py > test_results.txt 2>&1
type test_results.txt
