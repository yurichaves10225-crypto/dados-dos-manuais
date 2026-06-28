#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gerador de curvas de nível a partir do Copernicus GLO-30 DEM (open data, AWS).

Reaponte para o SEU talhão/vinhedo e gere curvas de nível, declividade e mapa.

Exemplos:
  # por bounding box (minlon minlat maxlon maxlat) com curvas de 5 m
  python gerar_curvas_nivel.py --bbox -52.560 -30.575 -52.490 -30.515 -i 5 -o saida_meu_vinhedo

  # por arquivo de limite do talhão (.geojson, .kml ou .shp)
  python gerar_curvas_nivel.py --limite meu_talhao.geojson -i 2 -o saida_meu_vinhedo

Requisitos: numpy rasterio shapely geopandas matplotlib requests
O DEM é baixado automaticamente do bucket público s3://copernicus-dem-30m.
"""
import argparse, math, os, sys, tempfile
import numpy as np
import requests
import rasterio
from rasterio.merge import merge
from rasterio.mask import mask as rio_mask
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from shapely.geometry import box, mapping, LineString
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm

WGS84 = "EPSG:4326"
S3 = "https://copernicus-dem-30m.s3.amazonaws.com"


def utm_epsg(lon, lat):
    zone = int((lon + 180) // 6) + 1
    return f"EPSG:{(32700 if lat < 0 else 32600) + zone}"


def tiles_for_bbox(minx, miny, maxx, maxy):
    names = []
    for la in range(math.floor(miny), math.floor(maxy) + 1):
        for lo in range(math.floor(minx), math.floor(maxx) + 1):
            ns = f"S{abs(la):02d}" if la < 0 else f"N{la:02d}"
            ew = f"W{abs(lo):03d}" if lo < 0 else f"E{lo:03d}"
            names.append(f"Copernicus_DSM_COG_10_{ns}_00_{ew}_00_DEM")
    return names


def download_tiles(names, cache):
    os.makedirs(cache, exist_ok=True)
    paths = []
    for n in names:
        p = os.path.join(cache, n + ".tif")
        if not os.path.exists(p):
            url = f"{S3}/{n}/{n}.tif"
            print(f"  baixando {n} ...")
            r = requests.get(url, timeout=600)
            if r.status_code != 200:
                print(f"  (tile inexistente: {n} HTTP {r.status_code}) — ignorado")
                continue
            open(p, "wb").write(r.content)
        paths.append(p)
    if not paths:
        sys.exit("Nenhum tile DEM disponível para a área pedida.")
    return paths


def contours(dem, meta, interval, clip_geom=None):
    t = meta["transform"]; h, w = dem.shape
    xs = t.c + t.a * (np.arange(w) + 0.5)
    ys = t.f + t.e * (np.arange(h) + 0.5)
    X, Y = np.meshgrid(xs, ys)
    Z = np.where(np.isnan(dem), np.nan, dem)
    lo = math.floor(np.nanmin(Z) / interval) * interval
    hi = math.ceil(np.nanmax(Z) / interval) * interval
    levels = np.arange(lo, hi + interval, interval)
    cs = plt.contour(X, Y, Z, levels=levels)
    recs = []
    for lvl, segs in zip(cs.levels, cs.allsegs):
        for seg in segs:
            if len(seg) >= 2:
                ln = LineString(seg)
                if ln.length > 0:
                    recs.append({"elev_m": float(lvl), "geometry": ln})
    plt.close("all")
    gdf = gpd.GeoDataFrame(recs, crs=meta["crs"])
    if clip_geom is not None and len(gdf):
        gdf = gpd.clip(gdf, clip_geom)
        gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()].reset_index(drop=True)
    return gdf


def slope_pct(dem, meta):
    t = meta["transform"]; px = abs(t.a); py = abs(t.e)
    z = dem.astype("float64")
    dzdx = np.gradient(z, px, axis=1); dzdy = np.gradient(z, py, axis=0)
    return np.tan(np.arctan(np.sqrt(dzdx**2 + dzdy**2))) * 100.0


def hillshade(dem, meta, az=315, alt=45):
    t = meta["transform"]; px = abs(t.a); py = abs(t.e)
    z = dem.astype("float64")
    dzdx = np.gradient(z, px, axis=1); dzdy = np.gradient(z, py, axis=0)
    slope = np.pi/2 - np.arctan(np.sqrt(dzdx**2 + dzdy**2))
    aspect = np.arctan2(-dzdx, dzdy)
    azr = np.radians(360 - az + 90); altr = np.radians(alt)
    hs = np.sin(altr)*np.sin(slope) + np.cos(altr)*np.cos(slope)*np.cos(azr - aspect)
    return np.clip(hs, 0, 1)


def main():
    ap = argparse.ArgumentParser(description="Curvas de nível a partir do Copernicus GLO-30 DEM")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--bbox", nargs=4, type=float, metavar=("MINLON","MINLAT","MAXLON","MAXLAT"))
    g.add_argument("--limite", help="arquivo de limite do talhão (.geojson/.kml/.shp)")
    ap.add_argument("-i", "--intervalo", type=float, default=5.0, help="equidistância das curvas (m)")
    ap.add_argument("-o", "--out", default="saida_curvas", help="pasta de saída")
    ap.add_argument("--cache", default="dem_cache", help="pasta de cache dos tiles DEM")
    ap.add_argument("--mestra", type=float, default=None, help="intervalo das curvas mestras (m)")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    if args.bbox:
        minx, miny, maxx, maxy = args.bbox
        aoi_wgs = box(minx, miny, maxx, maxy)
    else:
        gdf_lim = gpd.read_file(args.limite).to_crs(WGS84)
        aoi_wgs = gdf_lim.union_all() if hasattr(gdf_lim, "union_all") else gdf_lim.unary_union
        minx, miny, maxx, maxy = aoi_wgs.bounds

    cx, cy = (minx+maxx)/2, (miny+maxy)/2
    epsg = utm_epsg(cx, cy)
    print(f"AOI: lon {minx:.4f}..{maxx:.4f}  lat {miny:.4f}..{maxy:.4f}  | CRS projetado {epsg}")

    print("Baixando DEM...")
    paths = download_tiles(tiles_for_bbox(minx, miny, maxx, maxy), args.cache)
    srcs = [rasterio.open(p) for p in paths]
    arr, tr = merge(srcs, nodata=srcs[0].nodata)
    meta = srcs[0].meta.copy(); meta.update(height=arr.shape[1], width=arr.shape[2],
                                            transform=tr, count=1)
    for s in srcs: s.close()

    buf = 0.005
    clip = box(minx-buf, miny-buf, maxx+buf, maxy+buf)
    with MemoryFile() as mf:
        with mf.open(**meta) as ds: ds.write(arr[0], 1)
        with mf.open() as ds:
            out, ot = rio_mask(ds, [mapping(clip)], crop=True)
            m = ds.meta.copy()
    m.update(height=out.shape[1], width=out.shape[2], transform=ot)

    # reprojeta p/ UTM (metros)
    dt, w, h = calculate_default_transform(m["crs"], epsg, m["width"], m["height"],
                  *rasterio.transform.array_bounds(m["height"], m["width"], m["transform"]))
    dem = np.empty((h, w), "float32")
    reproject(out[0], dem, src_transform=m["transform"], src_crs=m["crs"],
              dst_transform=dt, dst_crs=epsg, resampling=Resampling.bilinear,
              src_nodata=m.get("nodata"), dst_nodata=np.nan)
    mu = m.copy(); mu.update(crs=epsg, transform=dt, width=w, height=h, dtype="float32", nodata=np.nan)

    aoi_utm = gpd.GeoSeries([aoi_wgs], crs=WGS84).to_crs(epsg).iloc[0]

    print(f"Gerando curvas de nível ({args.intervalo:g} m)...")
    g = contours(dem, mu, args.intervalo, clip_geom=aoi_utm)
    g.to_crs(WGS84).to_file(os.path.join(args.out, "curvas_nivel.geojson"), driver="GeoJSON")
    try:
        g.to_crs(WGS84).to_file(os.path.join(args.out, "curvas_nivel.kml"), driver="KML")
    except Exception as e:
        print("  (KML não gerado:", e, ")")
    print(f"  {len(g)} curvas, {g.geometry.length.sum()/1000:.1f} km")

    # DEM recortado
    z = dem.copy()
    # mapa
    print("Gerando mapa...")
    t = mu["transform"]
    xs = t.c + t.a*(np.arange(dem.shape[1])+0.5); ys = t.f + t.e*(np.arange(dem.shape[0])+0.5)
    ext = [xs.min(), xs.max(), ys.min(), ys.max()]
    hs = hillshade(dem, mu)
    fig, ax = plt.subplots(figsize=(11,10))
    ax.imshow(hs, cmap="gray", extent=ext, origin="upper", alpha=0.55)
    im = ax.imshow(np.where(np.isfinite(dem),dem,np.nan), cmap="terrain", extent=ext, origin="upper", alpha=0.5)
    g.plot(ax=ax, color="#3a2a10", linewidth=0.5)
    mestra = args.mestra or args.intervalo*5
    gm = g[(np.round(g.elev_m/mestra)*mestra == g.elev_m)]
    if len(gm): gm.plot(ax=ax, color="#7a1010", linewidth=1.0)
    ax.set_title(f"Curvas de nível {args.intervalo:g} m (mestras {mestra:g} m)\nCopernicus GLO-30 | {epsg}", fontsize=10)
    ax.set_xlabel("Este (m)"); ax.set_ylabel("Norte (m)")
    plt.colorbar(im, ax=ax, shrink=0.7, label="Altitude (m)")
    ax.set_aspect("equal"); plt.tight_layout()
    plt.savefig(os.path.join(args.out, "mapa_curvas.png"), dpi=140); plt.close()

    # declividade
    sp = slope_pct(dem, mu)
    bounds=[0,3,8,13,20,45,200]; colors=["#1a9641","#a6d96a","#ffffbf","#fdae61","#d7191c","#7b0000"]
    cmap=ListedColormap(colors); norm=BoundaryNorm(bounds,cmap.N)
    fig, ax = plt.subplots(figsize=(11,10))
    ims=ax.imshow(sp, cmap=cmap, norm=norm, extent=ext, origin="upper")
    plt.colorbar(ims, ax=ax, shrink=0.7, ticks=bounds, label="Declividade (%)")
    ax.set_title("Declividade (classes Embrapa)\nCopernicus GLO-30 | "+epsg, fontsize=10)
    ax.set_aspect("equal"); plt.tight_layout()
    plt.savefig(os.path.join(args.out, "mapa_declividade.png"), dpi=140); plt.close()

    print("Concluído. Saída em:", os.path.abspath(args.out))


if __name__ == "__main__":
    main()
