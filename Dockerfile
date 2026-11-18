# Dockerfile pour CartaGen — Production DGRE (Debian Linux / Kali compatible)
FROM python:3.11-slim

# Définition des variables d'environnement
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    WORKSPACE_ROOT=/app \
    PORT=8000 \
    IN_DOCKER=true \
    MPLBACKEND=Agg

WORKDIR /app

# Installation des dépendances système (GDAL, PostGIS tools, TexLive pour PDFLaTeX, MDBtools/PyODBC, Polices)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gdal-bin \
    libgdal-dev \
    libpq-dev \
    unixodbc \
    unixodbc-dev \
    mdbtools \
    odbc-mdbtools \
    fonts-dejavu-core \
    fonts-liberation \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-lang-french \
    texlive-fonts-recommended \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && if [ -f /usr/lib/x86_64-linux-gnu/odbc/libmdbodbc.so ]; then \
         printf "[Microsoft Access Driver (*.mdb, *.accdb)]\nDescription=MDB Tools ODBC\nDriver=/usr/lib/x86_64-linux-gnu/odbc/libmdbodbc.so\nSetup=\nFileUsage=1\n" >> /etc/odbcinst.ini; \
       fi

# Copier les fichiers de dépendances Python
COPY requirements.txt /app/

# Installation des dépendances Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir pyodbc

# Copier l'ensemble du projet CartaGen (filtré par .dockerignore)
COPY . /app

# Création des répertoires de stockage temporaire, caches et logs
RUN mkdir -p /app/sandbox_runs/uploads /app/logs /app/figures /app/data/raw /app/zvec_store /app/images_temp

EXPOSE 8000

# Healthcheck HTTP interne
HEALTHCHECK --interval=20s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Commande de démarrage
CMD ["python", "run_app.py"]

