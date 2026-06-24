# Pin to bookworm (Debian 12) — Microsoft's apt repo does not yet have a
# trixie (Debian 13) release, which is what python:3.12-slim now tracks.
FROM python:3.12-slim-bookworm

# Install Azure CLI via Microsoft's apt repo. Installing it via pip causes
# the dependency resolver to backtrack through hundreds of azure-cli versions
# when it is combined with the app's Azure SDK packages in a single pip solve.
#
# Side-effect: the azure-cli apt package deposits Azure SDK stub packages into
# the system Python, which corrupts the azure.* namespace when pip then installs
# the real azure-mgmt-* packages on top. A virtual environment for the app
# packages prevents the two sets of packages from ever merging.
RUN apt-get update && apt-get install -y curl ca-certificates gnupg \
    && curl -sLS https://packages.microsoft.com/keys/microsoft.asc \
       | gpg --dearmor -o /etc/apt/keyrings/microsoft.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/microsoft.gpg] \
       https://packages.microsoft.com/repos/azure-cli/ bookworm main" \
       > /etc/apt/sources.list.d/azure-cli.list \
    && apt-get update && apt-get install -y azure-cli \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY app/requirements.txt .
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

EXPOSE 8080

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
