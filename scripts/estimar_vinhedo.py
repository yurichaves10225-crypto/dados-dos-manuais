#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Estipula uma localizacao plausivel para vinhedos no municipio de Encruzilhada
do Sul, a partir de criterios de aptidao do relevo (altitude elevada, declividade
moderada), e gera curvas de nivel + declividade para essa area.
"""
import os, numpy as np, rasterio, geopandas as gpd
from rasterio.transform import xy
from shapely.geometry import box, mapping
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import curvas as C

ROOT = "/home/user/dados-dos-manuais"
ds = rasterio.open(os.path.join(ROOT, "dados", "dem_encruzilhada_utm22s.tif"))
dem = ds.read(1).astype("float64")
dem[dem == ds.nodata] = np.nan
t = ds.transform; px = abs(t.a); py = abs(t.e)
meta = {"transform": t, "crs": ds.crs, "width": ds.width, "height": ds.height, "nodata": np.nan}

# declividade (%)
dzdx = np.gradient(dem, px, axis=1); dzdy = np.gradient(dem, py, axis=0)
slope = np.tan(np.arctan(np.sqrt(dzdx**2 + dzdy**2))) * 100.0

# janela ~3.5 km
win_m = 3500
wpx = int(win_m / px)
step = max(1, wpx // 3)

def block_mean(a, r0, c0, n):
    b = a[r0:r0+n, c0:c0+n]
    return np.nanmean(b), np.nanmean(np.isfinite(b))

best = None
H, W = dem.shape
for r0 in range(0, H - wpx, step):
    for c0 in range(0, W - wpx, step):
        z_m, cov = block_mean(dem, r0, c0, wpx)
        if cov < 0.98 or not np.isfinite(z_m):
            continue
        s_m, _ = block_mean(slope, r0, c0, wpx)
        if not np.isfinite(s_m):
            continue
        # aptidao: altitude alta (bom ate ~450 m) + declividade moderada (alvo ~8%)
        score_alt = min(z_m, 450) / 450.0
        score_slp = max(0.0, 1.0 - abs(s_m - 8.0) / 12.0)  # otimo perto de 8%, penaliza extremos
        frac_steep, _ = block_mean((slope > 45).astype(float), r0, c0, wpx)
        score = score_alt * 0.5 + score_slp * 0.5 - frac_steep * 0.5
        if best is None or score > best[0]:
            best = (score, r0, c0, z_m, s_m)

_, r0, c0, z_m, s_m = best
# centro da janela -> lon/lat
cr, cc = r0 + wpx // 2, c0 + wpx // 2
cx, cy = xy(t, cr, cc)
import pyproj
tr = pyproj.Transformer.from_crs(ds.crs, "EPSG:4326", always_xy=True)
clon, clat = tr.transform(cx, cy)
print(f"Centro estimado: lon={clon:.5f} lat={clat:.5f}  alt_media={z_m:.0f} m  decliv_media={s_m:.1f}%")

# bbox em UTM -> WGS84
half = win_m / 2
bb_utm = box(cx-half, cy-half, cx+half, cy+half)
bb_wgs = gpd.GeoSeries([bb_utm], crs=ds.crs).to_crs("EPSG:4326").iloc[0]
print("bbox WGS84:", [round(v,5) for v in bb_wgs.bounds])

# recorta DEM e gera saidas
xs = t.c + t.a*(np.arange(W)+0.5); ys = t.f + t.e*(np.arange(H)+0.5)
cxsel = (xs>=cx-half)&(xs<=cx+half); cysel=(ys>=cy-half)&(ys<=cy+half)
demv = dem[np.ix_(cysel, cxsel)]; xv=xs[cxsel]; yv=ys[cysel]
from rasterio.transform import from_origin
mv = dict(meta); mv["transform"] = from_origin(xv.min()-px/2, yv.max()+py/2, px, py)
mv["width"]=demv.shape[1]; mv["height"]=demv.shape[0]

# curvas 5 m (e mestras 25 m), recortadas no bbox
gv = C.contours(demv, mv, interval=5, clip_geom_utm=bb_utm)
gw = gv.to_crs("EPSG:4326")
OUT = os.path.join(ROOT, "saida")
gw.to_file(os.path.join(OUT, "curvas_vinhedo_estimado_5m.geojson"), driver="GeoJSON")
gw.to_file(os.path.join(OUT, "curvas_vinhedo_estimado_5m.kml"), driver="KML")
gpd.GeoDataFrame({"nome":["vinhedo_estimado (aptidao de relevo)"],
                  "alt_media_m":[round(z_m)],"decliv_media_pct":[round(s_m,1)]},
                 geometry=[bb_wgs], crs="EPSG:4326").to_file(
    os.path.join(ROOT,"dados","vinhedo_estimado_bbox.geojson"), driver="GeoJSON")
print(f"{len(gv)} curvas, {gv.geometry.length.sum()/1000:.0f} km")

# slope da janela
sv = slope[np.ix_(cysel, cxsel)]
ext=[xv.min(),xv.max(),yv.min(),yv.max()]
hs = C.hillshade(demv, mv)

# mapa curvas
fig, ax = plt.subplots(figsize=(11,10))
ax.imshow(hs, cmap="gray", extent=ext, origin="upper", alpha=0.55)
im=ax.imshow(np.where(np.isfinite(demv),demv,np.nan), cmap="terrain", extent=ext, origin="upper", alpha=0.5)
gv.plot(ax=ax, color="#3a2a10", linewidth=0.5)
g25=gv[(gv.elev_m%25)==0]; g25.plot(ax=ax, color="#7a1010", linewidth=1.0)
ax.set_title("Vinhedo (localização ESTIMADA por aptidão de relevo) — Encruzilhada do Sul/RS\n"
             f"Curvas 5 m (mestras 25 m) | alt.média {z_m:.0f} m, decliv.média {s_m:.1f}% | Copernicus GLO-30 | UTM 22S",
             fontsize=9)
ax.set_xlabel("Este (m)"); ax.set_ylabel("Norte (m)")
plt.colorbar(im, ax=ax, shrink=0.7, label="Altitude (m)")
ax.set_aspect("equal"); plt.tight_layout()
plt.savefig(os.path.join(OUT,"mapa_vinhedo_estimado_curvas.png"), dpi=140); plt.close()

# mapa declividade
bounds=[0,3,8,13,20,45,200]; colors=["#1a9641","#a6d96a","#ffffbf","#fdae61","#d7191c","#7b0000"]
cmap=ListedColormap(colors); norm=BoundaryNorm(bounds,cmap.N)
fig, ax = plt.subplots(figsize=(11,10))
ims=ax.imshow(sv, cmap=cmap, norm=norm, extent=ext, origin="upper")
g25.plot(ax=ax, color="black", linewidth=0.4, alpha=0.5)
plt.colorbar(ims, ax=ax, shrink=0.7, ticks=bounds, label="Declividade (%)")
ax.set_title("Declividade — Vinhedo (localização ESTIMADA) Encruzilhada do Sul/RS\nClasses Embrapa | Copernicus GLO-30 | UTM 22S", fontsize=9)
ax.set_xlabel("Este (m)"); ax.set_ylabel("Norte (m)")
ax.set_aspect("equal"); plt.tight_layout()
plt.savefig(os.path.join(OUT,"mapa_vinhedo_estimado_declividade.png"), dpi=140); plt.close()
print("OK")
