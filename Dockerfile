# Use an official Python runtime as a parent image
FROM python:3.11-slim-bookworm

COPY requirements.txt /app_src/requirements.txt
# Set the source directory in the container
WORKDIR /app_src
# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Add current directory code to docker
COPY . /app_src

# Set this as the default command
ENTRYPOINT [ "python", "/app_src/epub_to_audiobook.py" ]