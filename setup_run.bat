@echo off
ECHO Setting up and running the Flask application...

:: Check if Python is installed
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    ECHO Python is not installed or not added to PATH. Please install Python and try again.
    PAUSE
    EXIT /B 1
)

:: Check if pip is available
pip --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    ECHO pip is not installed. Please ensure Python includes pip and try again.
    PAUSE
    EXIT /B 1
)

:: Check if requirements.txt exists
IF NOT EXIST requirements.txt (
    ECHO requirements.txt not found in the current directory. Creating one...
    ECHO flask==2.3.3> requirements.txt
    ECHO bcrypt==4.0.1>> requirements.txt
    ECHO pandas==2.0.3>> requirements.txt
    ECHO requests==2.31.0>> requirements.txt
    ECHO opencv-python==4.8.0.76>> requirements.txt
    ECHO fer==22.5.0>> requirements.txt
    ECHO reportlab==4.0.4>> requirements.txt
    ECHO python-dotenv==1.0.0>> requirements.txt
    ECHO numpy==1.24.3>> requirements.txt
    ECHO pillow==10.0.0>> requirements.txt
    ECHO matplotlib==3.7.2>> requirements.txt
    ECHO werkzeug==2.3.7>> requirements.txt
    ECHO jinja2==3.1.2>> requirements.txt
    ECHO gunicorn==20.1.0>> requirements.txt
)

:: Create and activate virtual environment
IF NOT EXIST venv (
    ECHO Creating virtual environment...
    python -m venv venv
    IF %ERRORLEVEL% NEQ 0 (
        ECHO Failed to create virtual environment.
        PAUSE
        EXIT /B 1
    )
)

ECHO Activating virtual environment...
CALL venv\Scripts\activate.bat
IF %ERRORLEVEL% NEQ 0 (
    ECHO Failed to activate virtual environment.
    PAUSE
    EXIT /B 1
)

:: Upgrade pip
ECHO Upgrading pip...
python -m pip install --upgrade pip
IF %ERRORLEVEL% NEQ 0 (
    ECHO Failed to upgrade pip.
    PAUSE
    EXIT /B 1
)

:: Install requirements
ECHO Installing dependencies from requirements.txt...
pip install -r requirements.txt
IF %ERRORLEVEL% NEQ 0 (
    ECHO Failed to install dependencies. Check requirements.txt for errors.
    PAUSE
    EXIT /B 1
)

:: Check if app.py exists
IF NOT EXIST app.py (
    ECHO app.py not found in the current directory. Please ensure app.py is present.
    PAUSE
    EXIT /B 1
)

:: Check if Ollama is installed and running
ECHO Checking if Ollama is installed and running...
ollama --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    ECHO Ollama is not installed or not added to PATH. Please install Ollama and try again.
    PAUSE
    EXIT /B 1
)

:: Start Ollama server in the background
ECHO Starting Ollama server...
start /B ollama serve
IF %ERRORLEVEL% NEQ 0 (
    ECHO Failed to start Ollama server. Ensure Ollama is properly installed.
    PAUSE
    EXIT /B 1
)

:: Wait briefly to ensure Ollama server starts
timeout /t 5

:: Check if gemma3n:e2b model is available
ECHO Checking for gemma3n:e2b model...
ollama list | findstr "gemma3n:e2b" >nul
IF %ERRORLEVEL% NEQ 0 (
    ECHO gemma3n:e2b model not found. Pulling model...
    ollama pull gemma3n:e2b
    IF %ERRORLEVEL% NEQ 0 (
        ECHO Failed to pull gemma3n:e2b model. Please check your Ollama setup.
        PAUSE
        EXIT /B 1
    )
)

:: Run the Flask app
ECHO Starting Flask application...
python app.py
IF %ERRORLEVEL% NEQ 0 (
    ECHO Failed to start Flask application. Check app.py for errors.
    PAUSE
    EXIT /B 1
)

PAUSE