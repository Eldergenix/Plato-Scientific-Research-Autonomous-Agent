# Use an official Python image as base
FROM python:3.12-slim

# Set environment variables to avoid interactive prompts during package installs
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies including LaTeX and some fonts for xelatex
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    texlive-xetex \
    texlive-science \
    texlive-publishers \
    texlive-plain-generic \
    fonts-freefont-ttf \
    fonts-dejavu \
    fonts-noto \
    fonts-liberation \
    fonts-inconsolata \
    fonts-texgyre \
    build-essential \
    git \
    curl \
    ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install the project into `/app`
WORKDIR /app

# Install
RUN pip install --no-cache-dir "denario[app]"

# This informs Docker that the container will listen on port 5000 at runtime.
EXPOSE 8501

# Touch a .env so it can be shared as a volume (being a single file instead of a folder requires this)
RUN touch .env

CMD ["denario", "run"]
