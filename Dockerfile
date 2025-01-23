# Use an official Python runtime as a parent image
FROM python:3.11-slim-bookworm

# Set the working directory inside the container
WORKDIR /app_src

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy only the requirements first to leverage Docker layer caching
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Add the rest of the application code
COPY . .

# Set the working directory to /app
WORKDIR /app

# Copy and configure the entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Set the entrypoint script as the default command
ENTRYPOINT ["/entrypoint.sh"]
