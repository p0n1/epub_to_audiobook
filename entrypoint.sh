#!/bin/sh

echo "Starting entrypoint script..."

if [ $# -eq 0 ] || { [ "$1" = "--host" ] || [ "$1" = "--port" ]; }; then
    # If no arguments or optional arguments --host and/or --port are provided, execute main_ui.py
    echo "No arguments or optional arguments provided. Executing main_ui.py"
    exec python3 /app_src/main_ui.py "$@"
elif [ "$1" = "python3" ] || [ "$1" = "python" ]; then
    # If the first argument is python or python3, execute the user-specified command
    echo "Executing user-specified python command: $@"
    exec "$@"
else
    # Otherwise, execute the default python3 /app_src/main.py command with all arguments
    echo "Executing default command: python3 /app_src/main.py $@"
    exec python3 /app_src/main.py "$@"
fi
