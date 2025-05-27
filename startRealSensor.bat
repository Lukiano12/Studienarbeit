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
REM If compilation doesn't work, try adapting the command as needed (see original comments)
cmake --build .
REM same here: cmake --build . --config Debug --target all -j 10

REM Change back to script directory before starting programs
cd /d "%SCRIPT_DIR%"

REM Start the C++ program in a new command prompt window
start /min "" cmd.exe /k "%SCRIPT_DIR%build\Studienarbeit.exe" 

REM Start the UI Python script in a new command prompt window
start /min "" cmd.exe /k python.exe "%SCRIPT_DIR%src\DataRetrievalAndUi\ui.py"

REM Start the real sensor Python script in a new command prompt window
start /min "" cmd.exe /k python.exe "%SCRIPT_DIR%src\DataRetrievalAndUi\getAnchorData.py"

REM For simulation only: comment out or remove the mockBluetooth line
REM start "" cmd.exe /k python.exe "%SCRIPT_DIR%src\DataRetrievalAndUi\mockBluetooth.py"