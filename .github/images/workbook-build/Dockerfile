FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates \
      python3 \
      python3-pip \
      texlive-xetex \
      texlive-lang-chinese \
      texlive-latex-extra \
      texlive-plain-generic \
      texlive-fonts-recommended \
      fonts-croscore \
      fontconfig \
      poppler-utils \
 && rm -rf /var/lib/apt/lists/*

COPY requirements-ci.txt requirements-pipeline.txt /tmp/workbook-requirements/
RUN python3 -m pip install --break-system-packages --no-cache-dir \
      -r /tmp/workbook-requirements/requirements-pipeline.txt

RUN xelatex --version | head -n 1 \
 && pdftoppm -v 2>&1 | head -n 1 \
 && test -n "$(kpsewhich FandolSong-Regular.otf)" \
 && test -n "$(kpsewhich FandolHei-Regular.otf)" \
 && test -n "$(kpsewhich FandolKai-Regular.otf)" \
 && fc-match Tinos | grep -qi tinos

WORKDIR /workspace
