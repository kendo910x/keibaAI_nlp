FROM localhost/nlp-hermes:0.22.2-stage3b
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
RUN /opt/nlp-db/venv/bin/pip install --no-cache-dir --only-binary=:all: \
        beautifulsoup4==4.15.0 soupsieve==4.1.3 playwright==1.65.2 \
    && /opt/nlp-db/venv/bin/pip check
ENV KEIBA_BROWSER_EXECUTABLE=/usr/bin/chromium
