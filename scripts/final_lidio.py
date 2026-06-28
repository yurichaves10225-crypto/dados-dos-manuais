#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recorte final ancorado na vinícola mais famosa do município (Lidio Carraro),
usando a coordenada documentada da sede de Encruzilhada do Sul como referência
aproximada (as coordenadas exatas das parcelas não são públicas).
Sede: 30°32'38"S 52°31'19"W  ->  lat -30.5439, lon -52.5219 (alt. ~432 m).
"""
import os, numpy as np, rasterio, geopandas as gpd, pyproj
from shapely.geometry import box
from rasterio.transform import from_origin
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import curvas as C

ROOT = "/home/user/dados-dos-manuais"
CLON, CLAT = -52.5219, -30.5439      # sede de Encruzilhada do Sul (referência)
HALF = 1750                           # metros -> janela de 3,5 km

ds = rasterio.open(os.path.join(ROOT, "dados", "dem_encruzilhada_utm22s.tif"))
dem = ds.read(1).astype("float64"); dem[dem == ds.nodata] = np.nan
t = ds.transform; px = abs(t.a); py = abs(t.e)
meta = {"transform": t, "crs": ds.crs, "width": ds.width, "height": ds.height, "nodata": np.nan}

# centro em UTM
fwd = pyproj.Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True)
cx, cy = fwd.transform(CLON, CLAT)
bb_utm = box(cx-HALF, cy-HALF, cx+HALF, cy+HALF)
bb_wgs = gpd.GeoSeries([bb_utm], crs=ds.crs).to_crs("EPSG:4326").iloc[0]

W = ds.width; H = ds.height
xs = t.c + t.a*(np.arange(W)+0.5); ys = t.f + t.e*(np.arange(H)+0.5)
cxsel = (xs>=cx-HALF)&(xs<=cx+HALF); cysel=(ys>=cy-HALF)&(ys<=cy+HALF)
demv = dem[np.ix_(cysel, cxsel)]; xv=xs[cxsel]; yv=ys[cysel]
mv = dict(meta); mv["transform"]=from_origin(xv.min()-px/2, yv.max()+py/2, px, py)
mv["width"]=demv.shape[1]; mv["height"]=demv.shape[0]
zmean = np.nanmean(demv)

# declividade
dzdx=np.gradient(demv,px,axis=1); dzdy=np.gradient(demv,py,axis=0)
slope=np.tan(np.arctan(np.sqrt(dzdx**2+dzdy**2)))*100
smean=np.nanmean(slope)
print(f"centro UTM=({cx:.0f},{cy:.0f})  alt.media={zmean:.0f} m  decliv.media={smean:.1f}%")

# curvas 5 m
gv = C.contours(demv, mv, interval=5, clip_geom_utm=bb_utm)
OUT = os.path.join(ROOT, "saida")
gv.to_crs("EPSG:4326").to_file(os.path.join(OUT,"curvas_lidio_carraro_aprox_5m.geojson"), driver="GeoJSON")
gv.to_crs("EPSG:4326").to_file(os.path.join(OUT,"curvas_lidio_carraro_aprox_5m.kml"), driver="KML")
gpd.GeoDataFrame({"nome":["Lidio Carraro (aprox. - sede municipal)"],
                  "ref":["30°32'38\"S 52°31'19\"W"],
                  "alt_media_m":[round(zmean)],"decliv_media_pct":[round(smean,1)]},
                 geometry=[bb_wgs], crs="EPSG:4326").to_file(
    os.path.join(ROOT,"dados","lidio_carraro_aprox_bbox.geojson"), driver="GeoJSON")
print(f"{len(gv)} curvas, {gv.geometry.length.sum()/1000:.0f} km")

ext=[xv.min(),xv.max(),yv.min(),yv.max()]; hs=C.hillshade(demv,mv)
# mapa curvas
fig,ax=plt.subplots(figsize=(11,10))
ax.imshow(hs,cmap="gray",extent=ext,origin="upper",alpha=0.55)
im=ax.imshow(np.where(np.isfinite(demv),demv,np.nan),cmap="terrain",extent=ext,origin="upper",alpha=0.5)
gv.plot(ax=ax,color="#3a2a10",linewidth=0.5)
g25=gv[(gv.elev_m%25)==0]; g25.plot(ax=ax,color="#7a1010",linewidth=1.0)
ax.plot(cx,cy,marker="*",color="navy",markersize=18,markeredgecolor="white")
ax.annotate("sede (ref.)",(cx,cy),color="navy",fontsize=9,xytext=(8,8),textcoords="offset points")
ax.set_title("Vinhedos Lidio Carraro (localização APROXIMADA — sede de Encruzilhada do Sul/RS)\n"
             f"Curvas 5 m (mestras 25 m) | alt.média {zmean:.0f} m, decliv.média {smean:.1f}% | Copernicus GLO-30 | UTM 22S",
             fontsize=9)
ax.set_xlabel("Este (m)"); ax.set_ylabel("Norte (m)")
plt.colorbar(im,ax=ax,shrink=0.7,label="Altitude (m)"); ax.set_aspect("equal"); plt.tight_layout()
plt.savefig(os.path.join(OUT,"mapa_lidio_carraro_aprox_curvas.png"),dpi=140); plt.close()
# mapa declividade
bounds=[0,3,8,13,20,45,200]; colors=["#1a9641","#a6d96a","#ffffbf","#fdae61","#d7191c","#7b0000"]
cmap=ListedColormap(colors); norm=BoundaryNorm(bounds,cmap.N)
fig,ax=plt.subplots(figsize=(11,10))
ims=ax.imshow(slope,cmap=cmap,norm=norm,extent=ext,origin="upper")
g25.plot(ax=ax,color="black",linewidth=0.4,alpha=0.5)
plt.colorbar(ims,ax=ax,shrink=0.7,ticks=bounds,label="Declividade (%)")
ax.set_title("Declividade — Vinhedos Lidio Carraro (APROX., sede de Encruzilhada do Sul/RS)\nClasses Embrapa | Copernicus GLO-30 | UTM 22S",fontsize=9)
ax.set_xlabel("Este (m)"); ax.set_ylabel("Norte (m)"); ax.set_aspect("equal"); plt.tight_layout()
plt.savefig(os.path.join(OUT,"mapa_lidio_carraro_aprox_declividade.png"),dpi=140); plt.close()
print("OK")
