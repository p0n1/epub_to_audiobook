#!/bin/sh

echo "Starting entrypoint script..."

if [ "$1" = "python3" ] || [ "$1" = "python" ]; then
    # If the first argument is python or python3, execute the user-specified command
    echo "Executing user-specified python command: $@"
    exec "$@"
else
    # Otherwise, execute the default python3 /app_src/main.py command with all arguments
    echo "Executing default command: python3 /app_src/main.py $@"
    exec python3 /app_src/main.py "$@"
fi