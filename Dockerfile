# Use an official Python runtime as a parent image
FROM python:3.11-slim-bookworm

# Set the working directory in the container
WORKDIR /app

# Add current directory code to docker
ADD . /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Set this as the default command
ENTRYPOINT [ "python", "epub_to_audiobook.py" ]
