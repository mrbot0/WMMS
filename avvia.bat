@echo off
rem Avvio con doppio clic. Per una prova senza modifiche: avvia.bat --anteprima
cd /d "%~dp0"
py -3.12 ottimizza_pc.py %*
if errorlevel 1 pause
