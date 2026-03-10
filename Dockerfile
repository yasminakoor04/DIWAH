# Simple container for the Dash dashboard
FROM python:3.12-slim

# Avoid interactive tzdata prompts
ENV DEBIAN_FRONTEND=noninteractive

# Workdir
WORKDIR /app

# System deps
RUN pip install --no-cache-dir --upgrade pip

# Install Python deps first for layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Expose Dash port
EXPOSE 8050

# Environment variables are provided via docker-compose.yml
# This keeps the Dockerfile clean and allows runtime configuration

# Run the dashboard
CMD ["python", "run_dashboard.py"]
