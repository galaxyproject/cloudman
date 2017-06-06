# Use base python image with Python 3.6
FROM python:3.6
# Use base Ubuntu 16.04 image
#FROM ubuntu:16.04

# Install system dependencies (for Ubuntu image)
#RUN apt-get update && apt-get install -y python-pip

# Add requirements.txt to the image
ADD requirements.txt /app/requirements.txt

# Set working directory to /app/
WORKDIR /app/

# Install python dependencies
RUN pip install -r requirements.txt

# Create unprivileged user
RUN adduser --disabled-password --gecos '' cloudman

# Add files to /app/
# This should probably be mounted at deployment step
ADD . /app
RUN chown -R cloudman:cloudman /app
