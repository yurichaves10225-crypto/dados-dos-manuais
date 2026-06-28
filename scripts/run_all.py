#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, json
import numpy as np
import rasterio
import geopandas as gpd
from shapely.geometry import shape, box, mapping
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
import curvas as C

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)               # raiz do repositorio
OUT = os.path.join(ROOT, "saida")
os.makedirs(OUT, exist_ok=True)
DEMDIR = os.path.join(ROOT, "dem")         # tiles brutos (rode scripts/baixar_dem.sh)
TILES = [os.path.join(DEMDIR, "S31_00_W053.tif"),
         os.path.join(DEMDIR, "S31_00_W054.tif")]
if not all(os.path.exists(t) for t in TILES):
    raise SystemExit("Tiles do DEM nao encontrados em ./dem — rode antes: bash scripts/baixar_dem.sh")

# limite municipal (WGS84)
muni = gpd.read_file(os.path.join(ROOT, "dados", "encruzilhada_limite.geojson"))
muni = muni.set_crs(C.WGS84) if muni.crs is None else muni.to_crs(C.WGS84)
muni_geom = muni.geometry.iloc[0]
muni_utm = muni.to_crs(C.UTM22S)
muni_geom_utm = muni_utm.geometry.iloc[0]

print(">> recortando DEM no municipio...")
dem_wgs, meta_wgs = C.mosaic_clip(TILES, muni_geom, buffer_deg=0.01)
print("   DEM wgs:", dem_wgs.shape)
dem_utm, meta_utm = C.to_utm(dem_wgs, meta_wgs)
print("   DEM utm:", dem_utm.shape, "res(m):", abs(meta_utm['transform'].a))

# salva DEM municipal (clip exato) comprimido
print(">> salvando DEM municipal (GeoTIFF comprimido)...")
from rasterio.mask import mask as rio_mask
from rasterio.io import MemoryFile
m = meta_utm.copy(); m.update(driver="GTiff", compress="deflate", predictor=3, tiled=True)
with MemoryFile() as mf:
    with mf.open(**m) as ds:
        ds.write(dem_utm.astype("float32"), 1)
    with mf.open() as ds:
        clip, ct = rio_mask(ds, [mapping(muni_geom_utm)], crop=True, nodata=np.nan)
        cm = ds.meta.copy(); cm.update(height=clip.shape[1], width=clip.shape[2],
                                       transform=ct, compress="deflate", predictor=3, tiled=True)
with rasterio.open(os.path.join(OUT, "dem_encruzilhada_utm22s.tif"), "w", **cm) as ds:
    ds.write(clip[0], 1)

elev = clip[0]
elev_valid = elev[np.isfinite(elev)]
print(f"   altitude: min={elev_valid.min():.0f} m  max={elev_valid.max():.0f} m  media={elev_valid.mean():.0f} m")

def export(gdf, name, descr, simplify_m=None):
    if simplify_m:
        gdf = gdf.copy()
        gdf["geometry"] = gdf.simplify(simplify_m, preserve_topology=False)
        gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()]
    gj = gdf.to_crs(C.WGS84)
    gj.to_file(os.path.join(OUT, name + ".geojson"), driver="GeoJSON")
    try:
        gj.to_file(os.path.join(OUT, name + ".kml"), driver="KML")
    except Exception as e:
        print("   (KML falhou:", e, ")")
    total_km = gdf.geometry.length.sum() / 1000.0
    print(f"   {name}: {len(gdf)} curvas, {total_km:.0f} km de linhas")

# ---- VISAO GERAL: municipio inteiro, intervalo 20 m ----
print(">> curvas de nivel do municipio (20 m)...")
g_muni = C.contours(dem_utm, meta_utm, interval=20, clip_geom_utm=muni_geom_utm)
export(g_muni, "curvas_municipio_20m", "Encruzilhada do Sul - 20 m", simplify_m=15)

# ---- AREA VITICOLA REPRESENTATIVA ----
# bbox ~ 6x6 km em zona de relevo ondulado dentro do municipio
VIN_BBOX = (-52.560, -30.575, -52.490, -30.515)  # minlon,minlat,maxlon,maxlat
vin_box_wgs = box(*VIN_BBOX)
vin_box_utm = gpd.GeoSeries([vin_box_wgs], crs=C.WGS84).to_crs(C.UTM22S).iloc[0]
print(">> curvas de nivel da area viticola (5 m)...")
g_vin = C.contours(dem_utm, meta_utm, interval=5, clip_geom_utm=vin_box_utm)
export(g_vin, "curvas_vinhedo_5m", "Area viticola - 5 m")
# declividade da area viticola
slope_deg, slope_pct = C.slope_aspect(dem_utm, meta_utm)

# salva bbox da area viticola
gpd.GeoDataFrame({"nome": ["area_viticola_exemplo"]}, geometry=[vin_box_wgs],
                 crs=C.WGS84).to_file(os.path.join(OUT, "area_viticola_bbox.geojson"),
                                      driver="GeoJSON")

# =================== MAPAS ===================
def crop_to_bbox(dem, meta, bbox_wgs):
    bb_utm = gpd.GeoSeries([box(*bbox_wgs)], crs=C.WGS84).to_crs(C.UTM22S).total_bounds
    t = meta["transform"]
    xs = t.c + t.a*(np.arange(dem.shape[1])+0.5)
    ys = t.f + t.e*(np.arange(dem.shape[0])+0.5)
    cx = (xs>=bb_utm[0])&(xs<=bb_utm[2]); cy=(ys>=bb_utm[1])&(ys<=bb_utm[3])
    return dem[np.ix_(cy,cx)], xs[cx], ys[cy]

# --- mapa municipio: hillshade + curvas 100 m destacadas ---
print(">> gerando mapa do municipio...")
t = meta_utm["transform"]
xs = t.c + t.a*(np.arange(dem_utm.shape[1])+0.5)
ys = t.f + t.e*(np.arange(dem_utm.shape[0])+0.5)
extent = [xs.min(), xs.max(), ys.min(), ys.max()]
hs = C.hillshade(dem_utm, meta_utm)
fig, ax = plt.subplots(figsize=(10,11))
ax.imshow(hs, cmap="gray", extent=extent, origin="upper", alpha=0.6)
demshow = np.where(np.isfinite(dem_utm), dem_utm, np.nan)
im = ax.imshow(demshow, cmap="terrain", extent=extent, origin="upper", alpha=0.5)
muni_utm.boundary.plot(ax=ax, color="black", linewidth=1.2)
g100 = g_muni[(g_muni.elev_m % 100)==0]
g100.plot(ax=ax, color="#5a3a1a", linewidth=0.4)
vin_g = gpd.GeoSeries([vin_box_utm], crs=C.UTM22S)
vin_g.boundary.plot(ax=ax, color="red", linewidth=1.8)
ax.set_title("Encruzilhada do Sul / RS — Relevo e curvas de nível (100 m)\nFonte: Copernicus GLO-30 DEM | UTM 22S", fontsize=11)
ax.set_xlabel("Este (m)"); ax.set_ylabel("Norte (m)")
plt.colorbar(im, ax=ax, shrink=0.6, label="Altitude (m)")
ax.set_aspect("equal"); plt.tight_layout()
plt.savefig(os.path.join(OUT, "mapa_municipio.png"), dpi=130); plt.close()

# --- mapa area viticola: hillshade + curvas 5m + rotulos 25m ---
print(">> gerando mapa da area viticola...")
demv, xv, yv = crop_to_bbox(dem_utm, meta_utm, VIN_BBOX)
metav = meta_utm.copy()
from rasterio.transform import from_origin
metav["transform"] = from_origin(xv.min()-abs(t.a)/2, yv.max()+abs(t.e)/2, abs(t.a), abs(t.e))
extv = [xv.min(), xv.max(), yv.min(), yv.max()]
hsv = C.hillshade(demv, metav)
fig, ax = plt.subplots(figsize=(11,10))
ax.imshow(hsv, cmap="gray", extent=extv, origin="upper", alpha=0.55)
imv = ax.imshow(np.where(np.isfinite(demv),demv,np.nan), cmap="terrain", extent=extv, origin="upper", alpha=0.5)
gv = g_vin.copy()
gv.plot(ax=ax, color="#3a2a10", linewidth=0.5)
g25 = gv[(gv.elev_m % 25)==0]
g25.plot(ax=ax, color="#7a1010", linewidth=1.0)
ax.set_title("Área vitícola (exemplo) — Encruzilhada do Sul/RS\nCurvas de nível 5 m (mestras 25 m em vermelho) | Copernicus GLO-30 | UTM 22S", fontsize=10)
ax.set_xlabel("Este (m)"); ax.set_ylabel("Norte (m)")
plt.colorbar(imv, ax=ax, shrink=0.7, label="Altitude (m)")
ax.set_aspect("equal"); plt.tight_layout()
plt.savefig(os.path.join(OUT, "mapa_vinhedo_curvas.png"), dpi=140); plt.close()

# --- mapa declividade area viticola ---
print(">> gerando mapa de declividade...")
slv, sxv, syv = crop_to_bbox(slope_pct, meta_utm, VIN_BBOX)
fig, ax = plt.subplots(figsize=(11,10))
from matplotlib.colors import BoundaryNorm, ListedColormap
bounds=[0,3,8,13,20,45,100]
colors=["#1a9641","#a6d96a","#ffffbf","#fdae61","#d7191c","#7b0000"]
cmap=ListedColormap(colors); norm=BoundaryNorm(bounds,cmap.N)
ims=ax.imshow(slv, cmap=cmap, norm=norm, extent=extv, origin="upper")
g25.plot(ax=ax, color="black", linewidth=0.4, alpha=0.5)
cb=plt.colorbar(ims, ax=ax, shrink=0.7, ticks=bounds, label="Declividade (%)")
ax.set_title("Declividade — Área vitícola (exemplo) Encruzilhada do Sul/RS\nClasses Embrapa | Copernicus GLO-30 | UTM 22S", fontsize=10)
ax.set_xlabel("Este (m)"); ax.set_ylabel("Norte (m)")
ax.set_aspect("equal"); plt.tight_layout()
plt.savefig(os.path.join(OUT, "mapa_vinhedo_declividade.png"), dpi=140); plt.close()

print("OK. Arquivos em", OUT)
for f in sorted(os.listdir(OUT)):
    sz=os.path.getsize(os.path.join(OUT,f))/1e6
    print(f"   {f}  ({sz:.2f} MB)")
