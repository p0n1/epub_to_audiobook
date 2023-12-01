# Use an official Python runtime as a parent image
FROM python:3.11-slim-bookworm

# Set the source directory in the container
WORKDIR /app_src

# Add current directory code to docker
ADD . /app_src

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Set the working directory to /app
WORKDIR /app

# Set this as the default command
ENTRYPOINT [ "python", "/app_src/main.py" ]