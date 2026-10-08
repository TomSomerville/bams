@echo off
rem BAMS command line (installed copy). Run it from an administrator Command Prompt, e.g.
rem   "C:\Program Files\BAMS\bams.cmd" user passwd NAME     (set a forgotten password)
rem   "C:\Program Files\BAMS\bams.cmd" status
if not defined BAMS_DATA_DIR set "BAMS_DATA_DIR=%ProgramData%\BAMS"
"%~dp0python\python.exe" -m bams %*
