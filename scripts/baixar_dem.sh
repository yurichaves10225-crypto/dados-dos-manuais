#!/usr/bin/env bash
# Baixa os tiles do Copernicus GLO-30 DEM que cobrem Encruzilhada do Sul/RS.
# Bucket público de open data (AWS), sem autenticação.
set -euo pipefail
DEST="${1:-dem}"
mkdir -p "$DEST"
BASE="https://copernicus-dem-30m.s3.amazonaws.com"
for T in S31_00_W053 S31_00_W054; do
  N="Copernicus_DSM_COG_10_${T}_00_DEM"
  echo "baixando $N ..."
  curl -sS -o "$DEST/${T}.tif" "$BASE/$N/$N.tif"
done
echo "DEM em $DEST/"
