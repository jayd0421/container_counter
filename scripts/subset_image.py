import streamlit as st
from pathlib import Path
from PIL import Image
import rasterio
from rasterio.windows import Window
import math
import os
import json
import shutil

def tiff_to_jpeg(tiff_path, jpeg_path=None, quality=95):
    """
    Convert a TIFF image to JPEG.

    Parameters
    ----------
    tiff_path : str or Path
        Path to the input TIFF file.
    jpeg_path : str or Path, optional
        Path to save the output JPEG. If not provided, uses the same name with .jpg.
    quality : int
        JPEG quality from 1 to 100.
    """
    
    os.makedirs("outputs/", exist_ok=True)
    tiff_path = Path(tiff_path)
    
    if jpeg_path is None:
        jpeg_path = tiff_path.with_suffix(".jpg")
    else:
        jpeg_path = Path(jpeg_path)

    with Image.open(tiff_path) as img:
        # JPEG does not support alpha or some TIFF modes, so convert to RGB
        img = img.convert("RGB")
        img.save(jpeg_path, "JPEG", quality=quality)

    return jpeg_path

def tile_jpeg_preview_with_metadata(
    jpeg_path,
    tiff_path,
    rows,
    cols,
    output_dir,
    prefix=None,
    quality=95
):
    """
    Tile a JPEG preview image using user-specified rows and columns,
    and save metadata that links each JPEG tile back to the original TIFF.

    Parameters
    ----------
    jpeg_path : str or Path
        Path to the JPEG preview image shown to the user.
    tiff_path : str or Path
        Path to the original TIFF image.
    rows : int
        Number of tile rows specified by the user.
    cols : int
        Number of tile columns specified by the user.
    output_dir : str or Path
        Folder where JPEG tiles and metadata JSON will be saved.
    prefix : str, optional
        Prefix for output tile names.
    quality : int
        JPEG output quality.

    Returns
    -------
    dict
        Full tiling metadata.
    """

    jpeg_path = Path(jpeg_path)
    tiff_path = Path(tiff_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if prefix is None:
        prefix = jpeg_path.stem

    with Image.open(jpeg_path) as jpeg_img, Image.open(tiff_path) as tiff_img:
        jpeg_img = jpeg_img.convert("RGB")

        jpeg_width, jpeg_height = jpeg_img.size
        tiff_width, tiff_height = tiff_img.size

        scale_x = tiff_width / jpeg_width
        scale_y = tiff_height / jpeg_height

        tile_width = math.ceil(jpeg_width / cols)
        tile_height = math.ceil(jpeg_height / rows)

        tiles = []

        for row in range(rows):
            for col in range(cols):
                jpeg_left = col * tile_width
                jpeg_top = row * tile_height
                jpeg_right = min(jpeg_left + tile_width, jpeg_width)
                jpeg_bottom = min(jpeg_top + tile_height, jpeg_height)

                tile = jpeg_img.crop(
                    (jpeg_left, jpeg_top, jpeg_right, jpeg_bottom)
                )

                tile_name = f"{prefix}_r{row + 1}_c{col + 1}.jpg"
                tile_path = output_dir / tile_name

                tile.save(tile_path, "JPEG", quality=quality)

                tiff_left = round(jpeg_left * scale_x)
                tiff_top = round(jpeg_top * scale_y)
                tiff_right = round(jpeg_right * scale_x)
                tiff_bottom = round(jpeg_bottom * scale_y)

                tiles.append({
                    "tile_name": tile_name,
                    "row": row + 1,
                    "col": col + 1,

                    "jpeg_bounds": {
                        "left": jpeg_left,
                        "top": jpeg_top,
                        "right": jpeg_right,
                        "bottom": jpeg_bottom,
                        "width": jpeg_right - jpeg_left,
                        "height": jpeg_bottom - jpeg_top
                    },

                    "tiff_bounds": {
                        "left": tiff_left,
                        "top": tiff_top,
                        "right": tiff_right,
                        "bottom": tiff_bottom,
                        "width": tiff_right - tiff_left,
                        "height": tiff_bottom - tiff_top
                    }
                })

        metadata = {
            "source_tiff": str(tiff_path),
            "source_jpeg": str(jpeg_path),
            "rows": rows,
            "cols": cols,
            "jpeg_size": {
                "width": jpeg_width,
                "height": jpeg_height
            },
            "tiff_size": {
                "width": tiff_width,
                "height": tiff_height
            },
            "scale": {
                "x": scale_x,
                "y": scale_y
            },
            "tiles": tiles
        }

        metadata_path = output_dir / f"{prefix}_tile_metadata.json"

        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=4)

    return metadata

def clear_tiles_output_folder(tiles_output_path):
    """
    Clear the existing image tiles when rows or columns change.
    """
    
    tiles_output_path = Path(tiles_output_path)
    
    if tiles_output_path.exists():
        shutil.rmtree(tiles_output_path)

    tiles_output_path.mkdir(parents=True, exist_ok=True)

    # Optional: clear selected tile from session state
    if "selected_tile" in st.session_state:
        del st.session_state["selected_tile"]

    st.session_state["tiles_cleared"] = True

def list_files_in_folder(folder_path):
    """
    Returns a list of file names in the given folder.
    Only regular files are included (no directories).
    """
    files = []
    try:
        # Check if the path exists and is a directory
        if not os.path.exists(folder_path):
            raise FileNotFoundError(f"Path does not exist: {folder_path}")
        if not os.path.isdir(folder_path):
            raise NotADirectoryError(f"Not a directory: {folder_path}")

        # Use scandir for efficiency
        with os.scandir(folder_path) as entries:
            for entry in entries:
                if entry.is_file():
                    if entry.name.split(".")[-1] == "jpg":
                        files.append(f"{folder_path}/{entry.name}")

    except (FileNotFoundError, NotADirectoryError) as e:
        print(f"Error: {e}")
    except PermissionError:
        print(f"Permission denied: {folder_path}")
    except Exception as e:
        print(f"Unexpected error: {e}")

    return files

from pathlib import Path
import re


def tile_to_tiff_bounds_from_selected_image(metadata, user_selected_image_path):
    """
    Return original TIFF pixel bounds for the selected JPEG tile.

    selected_image_path can be a full path or filename, for example:
    outputs/tiff_image_chips/tiff_image_r1_c4.jpeg
    """

    selected_image_name = Path(user_selected_image_path).name

    match = re.search(r"_r(\d+)_c(\d+)", selected_image_name)

    if not match:
        raise ValueError(
            f"Could not extract row/col from selected image name: {selected_image_name}"
        )

    row = int(match.group(1))
    col = int(match.group(2))

    for tile in metadata["tiles"]:
        if tile["row"] == row and tile["col"] == col:
            return tile["tiff_bounds"]

    raise ValueError(f"No tile found in metadata for row={row}, col={col}")

def crop_on_full_preview_to_tiff_bounds(
    metadata,
    crop_x,
    crop_y,
    crop_width,
    crop_height
):
    """
    Convert a crop drawn on the full JPEG preview image to original TIFF pixel bounds.
    """

    scale_x = metadata["scale"]["x"]
    scale_y = metadata["scale"]["y"]

    tiff_left = round(crop_x * scale_x)
    tiff_top = round(crop_y * scale_y)
    tiff_right = round((crop_x + crop_width) * scale_x)
    tiff_bottom = round((crop_y + crop_height) * scale_y)

    return {
        "left": tiff_left,
        "top": tiff_top,
        "right": tiff_right,
        "bottom": tiff_bottom,
        "width": tiff_right - tiff_left,
        "height": tiff_bottom - tiff_top
    }


def crop_tiff_using_bounds(
    tiff_path,
    output_path,
    bounds,
    overwrite=True
):
    """
    Crop original TIFF using pixel bounds.

    If overwrite=False and output_path already exists, an error is raised.
    """

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"{output_path} already exists. "
            "Use overwrite=True or choose a different output filename."
        )

    left = int(bounds["left"])
    top = int(bounds["top"])
    width = int(bounds["width"])
    height = int(bounds["height"])

    with rasterio.open(tiff_path) as src:
        window = Window(left, top, width, height)

        data = src.read(window=window)
        transform = src.window_transform(window)

        profile = src.profile.copy()
        profile.update({
            "height": height,
            "width": width,
            "transform": transform
        })

        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(data)

    return output_path