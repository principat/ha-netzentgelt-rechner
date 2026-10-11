#!/usr/bin/env bash
set -euo pipefail
mkdir -p .devconfig/custom_components
ln -sfn "$PWD/custom_components/netzentgelt_rechner" .devconfig/custom_components/netzentgelt_rechner
docker run --rm -p 8123:8123 -v "$PWD/.devconfig":/config ghcr.io/home-assistant/home-assistant:stable
