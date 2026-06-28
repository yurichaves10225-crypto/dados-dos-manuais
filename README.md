# Curvas de nível — vinhedos de Encruzilhada do Sul / RS

Geração de **curvas de nível**, **declividade** e **relevo sombreado** para a área
vitícola do município de **Encruzilhada do Sul (RS)**, a partir de um Modelo Digital
de Elevação (MDE) de domínio público.

Município de referência: **Encruzilhada do Sul/RS** — código IBGE `4306908`
(Serra do Sudeste / Campanha Gaúcha, região vitivinícola). Altitudes no município:
**~34 m a ~516 m**.

![Mapa da área vitícola](saida/mapa_vinhedo_curvas.png)

---

## O que tem aqui

```
dados/
  encruzilhada_limite.geojson        limite municipal (IBGE, WGS84)
  area_viticola_bbox.geojson         retângulo da área vitícola de exemplo
  dem_encruzilhada_utm22s.tif        MDE recortado no município (UTM 22S, metros)
saida/
  curvas_municipio_20m.geojson/.kml  curvas de nível do município (equidist. 20 m)
  curvas_vinhedo_5m.geojson/.kml     curvas da área vitícola (equidist. 5 m)
  mapa_municipio.png                 relevo + curvas (mestras de 100 m)
  mapa_vinhedo_curvas.png            relevo + curvas de 5 m (mestras de 25 m)
  mapa_vinhedo_declividade.png       declividade em classes Embrapa
scripts/
  gerar_curvas_nivel.py              CLI reutilizável — aponte para o SEU talhão
  curvas.py / run_all.py             pipeline que reproduz as saídas acima
  baixar_dem.sh                      baixa os tiles do MDE
```

Os arquivos `.kml` abrem direto no **Google Earth**; os `.geojson` e o `.tif`
abrem no **QGIS** (e em GIS web).

---

## Fonte de dados

- **MDE:** [Copernicus GLO-30 DEM](https://registry.opendata.aws/copernicus-dem/)
  (resolução ~30 m), bucket público de open data na AWS
  (`s3://copernicus-dem-30m`), sem autenticação.
- **Limite municipal:** malha de municípios do IBGE (via repositório
  [`tbrugz/geodata-br`](https://github.com/tbrugz/geodata-br)).
- **Sistema de coordenadas dos cálculos:** UTM 22S (`EPSG:32722`), em metros.
- **Declividade:** método de Horn (1981); classes de relevo conforme Embrapa
  (0–3% plano, 3–8% suave-ondulado, 8–13% ondulado, 13–20% ondulado/forte,
  20–45% forte-ondulado, >45% montanhoso).

> ⚠️ **Sobre a "área vitícola de exemplo":** este ambiente de execução não tem
> acesso ao OpenStreetMap/Overpass nem ao geoserviço do IBGE (bloqueados pela
> política de rede), então **não foi possível baixar automaticamente os polígonos
> exatos dos vinhedos mapeados**. A área de exemplo
> (`-52.560, -30.575, -52.490, -30.515`, ~6×7 km de relevo ondulado dentro do
> município) é **representativa**, para demonstrar o método. Para o seu vinhedo
> real, use o CLI abaixo apontando para as coordenadas ou o arquivo do talhão.

---

## Gerar curvas para o SEU vinhedo

```bash
pip install -r requirements.txt

# (a) por bounding box: minlon minlat maxlon maxlat, curvas de 5 m
python scripts/gerar_curvas_nivel.py \
    --bbox -52.560 -30.575 -52.490 -30.515 -i 5 -o saida_meu_vinhedo

# (b) por arquivo de limite do talhão (.geojson, .kml ou .shp), curvas de 2 m
python scripts/gerar_curvas_nivel.py \
    --limite meu_talhao.geojson -i 2 -o saida_meu_vinhedo
```

O script baixa sozinho os tiles do MDE necessários, reprojeta para UTM,
gera `curvas_nivel.geojson/.kml`, `mapa_curvas.png` e `mapa_declividade.png`.

Parâmetros: `-i/--intervalo` equidistância (m) · `--mestra` intervalo das
curvas mestras · `-o/--out` pasta de saída.

> O MDE tem resolução de ~30 m: curvas de 1–2 m carregam ruído. Para projeto de
> plantio em nível / terraços com precisão, use um levantamento topográfico
> (RTK/drone) e troque o MDE de entrada.

---

## Reproduzir as saídas deste repositório

```bash
pip install -r requirements.txt
bash scripts/baixar_dem.sh          # baixa os tiles para ./dem
python scripts/run_all.py           # regenera tudo em ./saida
```
