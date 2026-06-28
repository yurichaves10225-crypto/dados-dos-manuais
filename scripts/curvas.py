#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Geracao de curvas de nivel a partir do Copernicus GLO-30 DEM.
Uso interno do pipeline (chamado pelo run_all.py).
"""
import json
import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.mask import mask
from rasterio.warp import calculate_default_transform, reproject, Resampling, transform_bounds
from rasterio.transform import xy
from shapely.geometry import shape, box, LineString, mapping
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import geopandas as gpd

UTM22S = "EPSG:32722"   # Encruzilhada do Sul / RS
WGS84 = "EPSG:4326"


def mosaic_clip(tile_paths, geom_wgs84, buffer_deg=0.01):
    """Mosaica os tiles e recorta pela geometria (com pequeno buffer no bbox)."""
    srcs = [rasterio.open(p) for p in tile_paths]
    arr, transform = merge(srcs, nodata=srcs[0].nodata)
    meta = srcs[0].meta.copy()
    meta.update(height=arr.shape[1], width=arr.shape[2], transform=transform,
                count=1, dtype=arr.dtype)
    for s in srcs:
        s.close()
    # escreve mosaico em memoria e recorta
    from rasterio.io import MemoryFile
    minx, miny, maxx, maxy = geom_wgs84.bounds
    clip_geom = box(minx - buffer_deg, miny - buffer_deg,
                    maxx + buffer_deg, maxy + buffer_deg)
    with MemoryFile() as mf:
        with mf.open(**meta) as ds:
            ds.write(arr[0], 1)
        with mf.open() as ds:
            out, out_t = mask(ds, [mapping(clip_geom)], crop=True)
            out_meta = ds.meta.copy()
    out_meta.update(height=out.shape[1], width=out.shape[2], transform=out_t)
    return out[0], out_meta


def to_utm(dem, meta):
    """Reprojeta o DEM recortado para UTM 22S (metros)."""
    dst_crs = UTM22S
    transform, width, height = calculate_default_transform(
        meta["crs"], dst_crs, meta["width"], meta["height"],
        *rasterio.transform.array_bounds(meta["height"], meta["width"], meta["transform"]))
    dst = np.empty((height, width), dtype="float32")
    reproject(
        source=dem, destination=dst,
        src_transform=meta["transform"], src_crs=meta["crs"],
        dst_transform=transform, dst_crs=dst_crs,
        resampling=Resampling.bilinear,
        src_nodata=meta.get("nodata"), dst_nodata=np.nan)
    out_meta = meta.copy()
    out_meta.update(crs=dst_crs, transform=transform, width=width, height=height,
                    dtype="float32", nodata=np.nan, count=1)
    return dst, out_meta


def contours(dem_utm, meta_utm, interval, clip_geom_utm=None):
    """Gera curvas de nivel vetoriais (GeoDataFrame em UTM 22S)."""
    t = meta_utm["transform"]
    h, w = dem_utm.shape
    # grade de coordenadas (centro das celulas)
    xs = t.c + t.a * (np.arange(w) + 0.5)
    ys = t.f + t.e * (np.arange(h) + 0.5)
    X, Y = np.meshgrid(xs, ys)
    Z = np.where(np.isnan(dem_utm), np.nan, dem_utm)
    zmin = np.nanmin(Z); zmax = np.nanmax(Z)
    lo = np.floor(zmin / interval) * interval
    hi = np.ceil(zmax / interval) * interval
    levels = np.arange(lo, hi + interval, interval)
    cs = plt.contour(X, Y, Z, levels=levels)
    recs = []
    for level, segs in zip(cs.levels, cs.allsegs):
        for seg in segs:
            if len(seg) >= 2:
                ln = LineString(seg)
                if ln.length > 0:
                    recs.append({"elev_m": float(level), "geometry": ln})
    plt.close("all")
    gdf = gpd.GeoDataFrame(recs, crs=UTM22S)
    if clip_geom_utm is not None and len(gdf):
        gdf = gpd.clip(gdf, clip_geom_utm)
        gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()].reset_index(drop=True)
    return gdf


def slope_aspect(dem_utm, meta_utm):
    """Declividade (graus e %) por Horn (1981)."""
    t = meta_utm["transform"]
    px = abs(t.a); py = abs(t.e)
    z = dem_utm.astype("float64")
    dzdx = np.gradient(z, px, axis=1)
    dzdy = np.gradient(z, py, axis=0)
    slope_rad = np.arctan(np.sqrt(dzdx**2 + dzdy**2))
    slope_deg = np.degrees(slope_rad)
    slope_pct = np.tan(slope_rad) * 100.0
    return slope_deg, slope_pct


def hillshade(dem_utm, meta_utm, az=315, alt=45):
    t = meta_utm["transform"]
    px = abs(t.a); py = abs(t.e)
    z = dem_utm.astype("float64")
    dzdx = np.gradient(z, px, axis=1)
    dzdy = np.gradient(z, py, axis=0)
    slope = np.pi/2 - np.arctan(np.sqrt(dzdx**2 + dzdy**2))
    aspect = np.arctan2(-dzdx, dzdy)
    az_rad = np.radians(360 - az + 90)
    alt_rad = np.radians(alt)
    hs = (np.sin(alt_rad)*np.sin(slope) +
          np.cos(alt_rad)*np.cos(slope)*np.cos(az_rad - aspect))
    return np.clip(hs, 0, 1)
