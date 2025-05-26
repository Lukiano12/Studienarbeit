@echo off
set "SCRIPT_DIR=%~dp0"

REM Prompt user for log file name
set /p LOGFILE=Enter log file name (e.g. tag_log_20240526_153000.jsonl): 

REM Start the UI Python script in a new command prompt window
start "" cmd.exe /k python.exe "%SCRIPT_DIR%src\DataRetrievalAndUi\ui.py"

REM Start the replay logger in a new command prompt window with the chosen log file
start "" cmd.exe /k python.exe "%SCRIPT_DIR%src\DataRetrievalAndUi\replayLogger.py" "%SCRIPT_DIR%%LOGFILE%"