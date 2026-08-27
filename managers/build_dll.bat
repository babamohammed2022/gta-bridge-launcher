@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvars64.bat" >nul
cl /O2 /LD txdfix.c /Fe:txdfix.dll
