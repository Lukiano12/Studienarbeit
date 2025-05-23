@echo off

REM Set script directory variable at the very top!
set "SCRIPT_DIR=%~dp0"

REM Build the project using CMake
echo Building the project...
cd /d "%SCRIPT_DIR%"
if not exist build (
    mkdir build
)
cd build
cmake .. 
cmake --build . 

REM Change back to script directory before starting programs
cd /d "%SCRIPT_DIR%"

REM Start the C++ program in a new command prompt window
start "" cmd.exe /k "%SCRIPT_DIR%build\Studienarbeit.exe"

REM Start the first Python script in a new command prompt window
start "" cmd.exe /k python.exe "%SCRIPT_DIR%src\DataRetrievalAndUi\ui.py"

REM Start the second Python script in a new command prompt window
start "" cmd.exe /k python.exe "%SCRIPT_DIR%src\DataRetrievalAndUi\mockBluetooth.py"