#import libarraies
import streamlit as st

import torch
from segment_anything import sam_model_registry, SamAutomaticMaskGenerator

import rasterio
from rasterio.windows import Window
from rasterio.windows import from_bounds
from rasterio.mask import mask

import cv2
import matplotlib.pyplot as plt
import numpy as np
from rasterstats import zonal_stats

import laspy

import json
import geopandas as gpd

import pydeck as pdk

def generate_container_segment_masks(
    user_selected_image_path, 
    sam_model_path,
    points_per_side=32,
    pred_iou_thresh=0.80,
    stability_score_thresh=0.80,
    min_mask_region_area=500):
    
    with rasterio.open(user_selected_image_path) as src:
        user_selected_image = src.read([1, 2, 3]).transpose([1, 2, 0])
        
    #clear GPU memory
    torch.cuda.empty_cache()

    #load SAM ViT-B pretrained model
    sam = sam_model_registry["vit_b"](checkpoint=sam_model_path)
    sam.to("cuda" if torch.cuda.is_available() else "cpu")

    #model configuration
    mask_generator = SamAutomaticMaskGenerator(
        model=sam,
        points_per_side=points_per_side,
        pred_iou_thresh=pred_iou_thresh,
        stability_score_thresh=stability_score_thresh,
        min_mask_region_area=min_mask_region_area,
    )
    
    # mask_generator = SamAutomaticMaskGenerator(
    #     model=sam,
    #     points_per_side=64,
    #     crop_n_layers=1,
    #     crop_n_points_downscale_factor=2,
    #     pred_iou_thresh=0.90,
    #     stability_score_thresh=0.90,
    #     min_mask_region_area=1000,
    # )

    masks = mask_generator.generate(user_selected_image)
    
    return masks

def convert_masks_to_boxes(masks):
    boxes = []

    for mask in masks:
        # if (mask['area'] < 15000) and (mask['area'] > 2000):
            m = mask['segmentation'].astype(np.uint8)
            
            contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                continue
            cnt = max(contours, key=cv2.contourArea)
            rect = cv2.minAreaRect(cnt)

            (cx, cy), (bw, bh), angle = rect
            rect_global = ((cx, cy), (bw, bh), angle)

            # Store box with shape attributes for later filtering
            if min(bw, bh) > 0:
                boxes.append({
                    'rect': rect_global,
                    'area': mask['area'],
                    'aspect_ratio': max(bw, bh) / min(bw, bh),
                    'box_w': bw,
                    'box_h': bh
                })
        
    return boxes

def convert_boxes_to_geojson(boxes, user_selected_aoi_path, output_path):
    with rasterio.open(user_selected_aoi_path) as src:
        transform = src.transform
    
    def pixel_to_geo(px, py, transform):
        gx = transform.c + float(px) * transform.a
        gy = transform.f + float(py) * transform.e
        return gx, gy

    features = []
    for i, b in enumerate(boxes):
        box_points = cv2.boxPoints(b['rect'])

        geo_points = []
        for px, py in box_points:
            gx, gy = pixel_to_geo(px, py, transform)
            geo_points.append([gx, gy])
        geo_points.append(geo_points[0])  # close polygon

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [geo_points]
            },
            "properties": {
                "id": int(i),
                "area_px": float(round(b['area'], 2)),
                "aspect_ratio": float(round(b['aspect_ratio'], 2)),
                # "zone": "ship" if (9000 < b['rect'][0][0] < 10000 and
                #                    1000 < b['rect'][0][1] < 6000) else "yard"
            }
        }
        features.append(feature)

    geojson = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "EPSG:32631"}},
        "features": features
    }

    output_path = output_path
    with open(output_path, 'w') as f:
        json.dump(geojson, f)
        

def pixel_bounds_to_map_bounds(tiff_path, bounds):
    """
    Convert pixel crop bounds from the TIFF into map/CRS coordinates.

    Returns
    -------
    dict with xmin, ymin, xmax, ymax
    """

    left = int(bounds["left"])
    top = int(bounds["top"])
    width = int(bounds["width"])
    height = int(bounds["height"])

    with rasterio.open(tiff_path) as src:
        window = Window(left, top, width, height)

        # Returns bounds in the TIFF CRS: left, bottom, right, top
        xmin, ymin, xmax, ymax = src.window_bounds(window)

        return {
            "xmin": xmin,
            "ymin": ymin,
            "xmax": xmax,
            "ymax": ymax,
            "crs": src.crs
        }

def filter_las_by_map_bounds(las_path, output_las_path, map_bounds):
    """
    Filter a LAS/LAZ file using map bounds derived from a cropped TIFF.
    """

    las = laspy.read(las_path)

    x = las.x
    y = las.y

    mask = (
        (x >= map_bounds["xmin"]) &
        (x <= map_bounds["xmax"]) &
        (y >= map_bounds["ymin"]) &
        (y <= map_bounds["ymax"])
    )

    cropped_las = laspy.LasData(las.header)
    cropped_las.points = las.points[mask]

    cropped_las.write(output_las_path)
    
    return output_las_path


def add_las_elevation_stats(geojson_path, filtered_las_path):
    gdf = gpd.read_file(geojson_path)
    
    las = laspy.read(filtered_las_path)
    x = np.array(las.x)
    y = np.array(las.y)
    z = np.array(las.z)
    
    points_gdf = gpd.GeoDataFrame(
        {"z": z},
        geometry=gpd.points_from_xy(x, y),
        crs=gdf.crs
    )
    
    # Add polygon ID
    gdf = gdf.copy()
    gdf["id"] = gdf.index

    # Spatial join: assign each LiDAR point to a polygon
    joined = gpd.sjoin(
        points_gdf,
        gdf[["id", "geometry"]],
        how="inner",
        predicate="within"
    )
    
    stats = joined.groupby("id")["z"].agg(
    point_count="count",
        min_z="min",
        max_z="max",
        mean_z="mean",
        median_z="median",
        std_z="std"
    ).reset_index()

    gdf_stats = gdf.merge(stats, on="id", how="left")
    
    return gdf_stats

def crop_dsm_by_map_bounds(
    dsm_path,
    output_dsm_path,
    map_bounds
):
    """
    Crop a raster using map coordinate bounds.
    Useful for cropping DSM to match selected image area.
    """

    with rasterio.open(dsm_path) as src:
        window = from_bounds(
            map_bounds["xmin"],
            map_bounds["ymin"],
            map_bounds["xmax"],
            map_bounds["ymax"],
            transform=src.transform
        )

        window = window.round_offsets().round_lengths()

        data = src.read(window=window)
        transform = src.window_transform(window)

        profile = src.profile.copy()
        profile.update({
            "height": data.shape[1],
            "width": data.shape[2],
            "transform": transform
        })

        with rasterio.open(output_dsm_path, "w", **profile) as dst:
            dst.write(data)

    return output_dsm_path

def add_dsm_elevation_stats(
    container_boxes_gdf,
    dsm_tiff_path,
    polygon_id_col=None,
    stats=("count", "min", "max", "mean", "median", "std"),
    prefix="dsm_"
):
    """
    Add elevation statistics from a DSM TIFF to polygons.

    Parameters
    ----------
    geojson_path : str
        Path to polygon GeoJSON.
    dsm_tiff_path : str
        Path to DSM raster TIFF.
    polygon_id_col : str, optional
        Existing polygon ID column. If None, an 'id' column is created from the index.
    stats : tuple
        Zonal statistics to calculate.
    prefix : str
        Prefix added to output statistic columns.

    Returns
    -------
    GeoDataFrame
        Polygon GeoDataFrame with DSM elevation stats added.
    """
    gdf = container_boxes_gdf
    
    with rasterio.open(dsm_tiff_path) as src:
        raster_crs = src.crs
        nodata = src.nodata

    # Make sure polygons and DSM are in the same CRS
    if gdf.crs != raster_crs:
        gdf = gdf.to_crs(raster_crs)

    gdf = gdf.copy()

    if polygon_id_col is None:
        polygon_id_col = "id"
        gdf[polygon_id_col] = gdf.index

    zs = zonal_stats(
        vectors=gdf,
        raster=dsm_tiff_path,
        stats=list(stats),
        nodata=nodata,
        geojson_out=False,
        all_touched=False
    )

    stats_gdf = gdf.copy()

    for stat_name in stats:
        stats_gdf[f"{prefix}{stat_name}"] = [
            item.get(stat_name, None) for item in zs
        ]

    return stats_gdf

def filter_clean_container_boxes_gdf(container_boxes_gdf, ground_elevation=51):
    std_z_filter = 5 # to filter out very tall flood lights in image
    
    container_boxes_gdf = container_boxes_gdf[(container_boxes_gdf['std_z'] < std_z_filter)]
    
    container_boxes_gdf = container_boxes_gdf[(container_boxes_gdf['mean_z'] > 51)]
    
    container_boxes_gdf = container_boxes_gdf[(container_boxes_gdf['area_px'] > 2000) & (container_boxes_gdf['area_px'] < 15000)]
    
    container_boxes_gdf['elev'] = round(container_boxes_gdf['mean_z'] - container_boxes_gdf['dsm_mean'], 2)
    
    container_boxes_gdf = container_boxes_gdf[(container_boxes_gdf['elev'] > 3)]
    
    container_boxes_gdf['base_height'] = 0
    
    mask = container_boxes_gdf["elev"] > 18
    container_boxes_gdf.loc[mask, "elev"] -= 16
    container_boxes_gdf.loc[mask, "base_height"] = 16
    
    container_boxes_gdf['elev'] = round(container_boxes_gdf['elev'], 2)
    
    return container_boxes_gdf

def add_color_to_containers(user_selected_aoi_path, container_boxes_gdf):
    colors = []

    with rasterio.open(user_selected_aoi_path) as src:

        for geom in container_boxes_gdf.geometry:
            out_image, _ = mask(src, [geom], crop=True)

            # Assuming RGB raster with shape (bands, rows, cols)
            rgb = out_image[:3]

            # Remove nodata pixels
            valid = np.all(rgb > 0, axis=0)

            if valid.any():
                mean_color = [
                    int(rgb[0][valid].mean()),
                    int(rgb[1][valid].mean()),
                    int(rgb[2][valid].mean())
                ]
            else:
                mean_color = [128, 128, 128]

            colors.append(mean_color)

    container_boxes_gdf["color"] = colors
    
    return container_boxes_gdf

def plot_image(container_boxes_gdf, user_selected_aoi_path, image_out_path='outputs/preview_tiles/image.jpg'):
    with rasterio.open(user_selected_aoi_path) as src:
        selected_image = src.read([1, 2, 3]).transpose([1, 2, 0])
        bounds = src.bounds
    
    fig, ax = plt.subplots(figsize=(12, 12))

    # Plot raster using real-world coordinates
    ax.imshow(selected_image, extent=[
            bounds.left,
            bounds.right,
            bounds.bottom,
            bounds.top
        ])

    container_boxes_gdf.plot(ax=ax,
        facecolor="none",
        edgecolor="red",
        linewidth=1)
    ax.axis('off')
    # ax.set_title(f"{len(container_boxes_gdf)} boxes")
    plt.savefig(image_out_path, dpi=150, bbox_inches='tight')
    
    return image_out_path


def add_3d_visualisation(container_boxes_gdf):
    container_boxes_gdf = container_boxes_gdf.to_crs("EPSG:4326")
    from shapely.geometry import Polygon

    def add_z(poly, z):
        coords_3d = [(x, y, z) for x, y in poly.exterior.coords]
        return Polygon(coords_3d)

    container_boxes_gdf["geometry"] = container_boxes_gdf.apply(
        lambda row: add_z(row.geometry, row.base_height),
        axis=1
    )
    
    container_boxes_gdf = container_boxes_gdf.to_crs(4326)
    
    layer = pdk.Layer(
        "PolygonLayer",
        data=container_boxes_gdf,
        get_polygon="geometry.coordinates",
        get_fill_color="color",
        get_line_color=[255, 255, 255],
        get_elevation="elev",
        extruded=True,
        # wireframe=True,
        pickable=True,
    )
    
    centroid = container_boxes_gdf.unary_union.centroid

    view_state = pdk.ViewState(
        latitude=centroid.y,
        longitude=centroid.x,
        zoom=17,
        pitch=60,
        bearing=30,
    )
    
    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_style=pdk.map_styles.LIGHT,
        # map_style="mapbox://styles/mapbox/satellite-v9",
        tooltip = {
            "html": """
            <b>Stack height:</b> {elev}<br>
    #       <b>Containers:</b> {n_containers}
            """,
            "style": {"color": "white"},
        },
        #  tooltip = {
        #     "html": """
        #     <b>Height:</b> {elev}<br>
        #     <b>mean_z:</b> {mean_z}<br>
        #     <b>median_z:</b> {median_z}<br>
        #     <b>dsm_mean:</b> {dsm_mean}<br>
        #     <b>dsm_median:</b> {dsm_median}
        #     """,
        #     "style": {"color": "white"},
        # },
    )
    
    # deck.to_html("test.html")
    st.pydeck_chart(deck)
    