FROM docker.io/nousresearch/hermes-agent:v0.22.2@sha256:a11574b7fe8e1631d7d88d556677dac693bc058abf558cdeb899155688c1bf05
COPY requirements.lock /opt/nlp-db/requirements.lock
RUN /opt/hermes/tools/python-3.14.7+20260901-linux-x64/bin/python3.14 -m venv /opt/nlp-db/venv \
    && /opt/nlp-db/venv/bin/python -m pip --disable-pip-version-check --isolated install \
        --no-cache-dir --only-binary=:all: --require-hashes -r /opt/nlp-db/requirements.lock \
    && /opt/nlp-db/venv/bin/python -m pip check
COPY server.py store.py targets.py /opt/nlp-db/
COPY AGENTS.md /opt/nlp-research/AGENTS.md
