#!/bin/sh
# Runs BAMS's server tests on Ubuntu 24.04's FFmpeg (6.1.1, the owner's server) inside Docker.
# The repo is mounted read-only at /src; the tests run on a copy. Arguments go to pytest.
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null
apt-get install -y -qq python3 python3-venv ffmpeg >/dev/null 2>&1
ffmpeg -hide_banner -version | head -1
mkdir -p /work && cp -r /src/server /work/ && cd /work/server
rm -rf .venv *.egg-info
python3 -m venv /venv
/venv/bin/pip install -q -e ".[dev]"
/venv/bin/python -m pytest -q -p no:cacheprovider "$@" 2>&1 | tail -40
