FROM python:3.12-slim

WORKDIR /app

# Install system dependencies including fonts for PDF generation
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    postgresql-client \
    fonts-dejavu \
    libyaml-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel cython
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

