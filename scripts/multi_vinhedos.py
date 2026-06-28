#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Seleciona N áreas vitícolas adicionais no município por aptidão de relevo
(altitude elevada + declividade moderada), bem separadas entre si e do ponto
já mapeado da Lidio Carraro, e gera curvas de nível (5 m), declividade e mapas.
"""
import os, numpy as np, rasterio, geopandas as gpd, pyproj
from shapely.geometry import box
from rasterio.transform import from_origin, xy
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import curvas as C

ROOT = "/home/user/dados-dos-manuais"
HALF = 1750                       # janela 3,5 km
SEP_M = 7000                      # separação mínima entre centros
N = 2                             # quantos vinhedos adicionais
# pontos já mapeados a evitar (Lidio Carraro)
AVOID_LL = [(-30.5439, -52.5219)]

ds = rasterio.open(os.path.join(ROOT, "dados", "dem_encruzilhada_utm22s.tif"))
dem = ds.read(1).astype("float64"); dem[dem == ds.nodata] = np.nan
t = ds.transform; px = abs(t.a); py = abs(t.e)
meta = {"transform": t, "crs": ds.crs, "width": ds.width, "height": ds.height, "nodata": np.nan}
H, W = dem.shape

dzdx = np.gradient(dem, px, axis=1); dzdy = np.gradient(dem, py, axis=0)
slope = np.tan(np.arctan(np.sqrt(dzdx**2 + dzdy**2))) * 100.0

fwd = pyproj.Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True)
inv = pyproj.Transformer.from_crs(ds.crs, "EPSG:4326", always_xy=True)
avoid_xy = [fwd.transform(lon, lat) for lat, lon in AVOID_LL]

wpx = int(2*HALF / px); step = max(1, wpx // 4)
def bmean(a, r0, c0, n):
    b = a[r0:r0+n, c0:c0+n]; return np.nanmean(b), np.nanmean(np.isfinite(b))

cands = []
for r0 in range(0, H - wpx, step):
    for c0 in range(0, W - wpx, step):
        z_m, cov = bmean(dem, r0, c0, wpx)
        if cov < 0.99 or not np.isfinite(z_m): continue
        s_m, _ = bmean(slope, r0, c0, wpx)
        if not np.isfinite(s_m): continue
        steep, _ = bmean((slope > 45).astype(float), r0, c0, wpx)
        score = min(z_m,450)/450*0.5 + max(0,1-abs(s_m-8)/12)*0.5 - steep*0.5
        cr, cc = r0 + wpx//2, c0 + wpx//2
        gx, gy = xy(t, cr, cc)
        cands.append((score, gx, gy, z_m, s_m))
cands.sort(reverse=True)

picked = []
for score, gx, gy, z_m, s_m in cands:
    if any((gx-ax)**2 + (gy-ay)**2 < SEP_M**2 for ax, ay in avoid_xy): continue
    if any((gx-px2)**2 + (gy-py2)**2 < SEP_M**2 for px2, py2, *_ in picked): continue
    picked.append((gx, gy, z_m, s_m, score))
    if len(picked) >= N: break

xs = t.c + t.a*(np.arange(W)+0.5); ys = t.f + t.e*(np.arange(H)+0.5)
OUT = os.path.join(ROOT, "saida")
bounds=[0,3,8,13,20,45,200]; cols=["#1a9641","#a6d96a","#ffffbf","#fdae61","#d7191c","#7b0000"]
cmap=ListedColormap(cols); norm=BoundaryNorm(bounds,cmap.N)

for i, (cx, cy, z_m, s_m, score) in enumerate(picked, start=2):  # numera 2 e 3
    lon, lat = inv.transform(cx, cy)
    nome = f"vinhedo_{i}"
    bb_utm = box(cx-HALF, cy-HALF, cx+HALF, cy+HALF)
    bb_wgs = gpd.GeoSeries([bb_utm], crs=ds.crs).to_crs("EPSG:4326").iloc[0]
    cxsel=(xs>=cx-HALF)&(xs<=cx+HALF); cysel=(ys>=cy-HALF)&(ys<=cy+HALF)
    demv=dem[np.ix_(cysel,cxsel)]; xv=xs[cxsel]; yv=ys[cysel]
    mv=dict(meta); mv["transform"]=from_origin(xv.min()-px/2,yv.max()+py/2,px,py)
    mv["width"]=demv.shape[1]; mv["height"]=demv.shape[0]
    slv=slope[np.ix_(cysel,cxsel)]
    print(f"{nome}: lat={lat:.5f} lon={lon:.5f}  alt.media={z_m:.0f} m  decliv.media={s_m:.1f}%")

    gv=C.contours(demv,mv,interval=5,clip_geom_utm=bb_utm)
    gv.to_crs("EPSG:4326").to_file(os.path.join(OUT,f"curvas_{nome}_5m.geojson"),driver="GeoJSON")
    gv.to_crs("EPSG:4326").to_file(os.path.join(OUT,f"curvas_{nome}_5m.kml"),driver="KML")
    gpd.GeoDataFrame({"nome":[f"Vinhedo {i} (aptidão de relevo)"],"lat":[round(lat,5)],
                      "lon":[round(lon,5)],"alt_media_m":[round(z_m)],
                      "decliv_media_pct":[round(s_m,1)]}, geometry=[bb_wgs],
                     crs="EPSG:4326").to_file(os.path.join(ROOT,"dados",f"{nome}_bbox.geojson"),driver="GeoJSON")

    ext=[xv.min(),xv.max(),yv.min(),yv.max()]; hs=C.hillshade(demv,mv)
    g25=gv[(gv.elev_m%25)==0]
    fig,ax=plt.subplots(figsize=(11,10))
    ax.imshow(hs,cmap="gray",extent=ext,origin="upper",alpha=0.55)
    im=ax.imshow(np.where(np.isfinite(demv),demv,np.nan),cmap="terrain",extent=ext,origin="upper",alpha=0.5)
    gv.plot(ax=ax,color="#3a2a10",linewidth=0.5); g25.plot(ax=ax,color="#7a1010",linewidth=1.0)
    ax.plot(cx,cy,marker="*",color="navy",markersize=20,markeredgecolor="white",zorder=5)
    ax.annotate(f"{lat:.4f}, {lon:.4f}",(cx,cy),color="navy",fontsize=9,xytext=(8,8),textcoords="offset points")
    ax.set_title(f"Vinhedo {i} (área vitícola por aptidão de relevo) — Encruzilhada do Sul/RS\n"
                 f"Curvas 5 m (mestras 25 m) | alt.média {z_m:.0f} m, decliv.média {s_m:.1f}% | Copernicus GLO-30 | UTM 22S",fontsize=9)
    ax.set_xlabel("Este (m)"); ax.set_ylabel("Norte (m)")
    plt.colorbar(im,ax=ax,shrink=0.7,label="Altitude (m)"); ax.set_aspect("equal"); plt.tight_layout()
    plt.savefig(os.path.join(OUT,f"mapa_{nome}_curvas.png"),dpi=140); plt.close()

    fig,ax=plt.subplots(figsize=(11,10))
    ims=ax.imshow(slv,cmap=cmap,norm=norm,extent=ext,origin="upper")
    g25.plot(ax=ax,color="black",linewidth=0.4,alpha=0.5)
    ax.plot(cx,cy,marker="*",color="navy",markersize=20,markeredgecolor="white",zorder=5)
    plt.colorbar(ims,ax=ax,shrink=0.7,ticks=bounds,label="Declividade (%)")
    ax.set_title(f"Declividade — Vinhedo {i} (aptidão de relevo) Encruzilhada do Sul/RS\nClasses Embrapa | Copernicus GLO-30 | UTM 22S",fontsize=9)
    ax.set_xlabel("Este (m)"); ax.set_ylabel("Norte (m)"); ax.set_aspect("equal"); plt.tight_layout()
    plt.savefig(os.path.join(OUT,f"mapa_{nome}_declividade.png"),dpi=140); plt.close()
print("OK")
