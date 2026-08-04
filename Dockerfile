# Multi-stage Dockerfile pour CartaGen - Production DGRE
FROM python:3.11-slim

# Définition des variables d'environnement
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    WORKSPACE_ROOT=/app

WORKDIR /app

# Installation des dépendances système (GDAL, PostGIS tools, TexLive pour PDFLaTeX, MDBtools/PyODBC)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gdal-bin \
    libgdal-dev \
    libpq-dev \
    unixodbc \
    unixodbc-dev \
    mdbtools \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-lang-french \
    texlive-fonts-recommended \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copier le fichier des dépendances Python
COPY requirements.txt /app/

# Installation des dépendances Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir pyodbc

# Copier l'ensemble du projet CartaGen
COPY . /app

# Création du dossier de stockage temporaire
RUN mkdir -p /app/sandbox_runs/uploads

EXPOSE 8000

# Commande de démarrage par défaut
CMD ["python", "run_app.py"]
