FROM python:3.12-slim

WORKDIR /app

COPY app/requirements.txt .
# Install Azure CLI via pip so DefaultAzureCredential can use az login tokens.
# This avoids apt repo issues with newer Debian releases.
RUN pip install --no-cache-dir -r requirements.txt azure-cli

COPY app/ .

EXPOSE 8080

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
