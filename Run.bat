@echo off
cd /d "D:\F.Forvia\P.Programming\2. Penguin\CKD"

start cmd /k python 0_Fake_server.py
timeout /t 2 >nul

start cmd /k python 1_SPI_Middleware_Palmi.py
timeout /t 2 >nul

start cmd /k python 2_CSVFile_Writer.py