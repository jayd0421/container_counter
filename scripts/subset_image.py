import streamlit as st
import os
from pathlib import Path
import re
from PIL import Image
import rasterio
from rasterio.windows import Window
import math
import json
import shutil
from datetime import datetime

def tiff_to_jpeg(tiff_path, jpeg_path=None, quality=95):
    """
    Convert a TIFF image to a JPEG preview image.

    The function opens a TIFF image, converts it to RGB, and saves it as a JPEG.
    This is useful for creating a lighter preview image from a large TIFF.

    Parameters
    ----------
    tiff_path : str or pathlib.Path
        Path to the input TIFF image.
    jpeg_path : str or pathlib.Path, optional
        Path where the output JPEG should be saved. If None, the JPEG is saved
        using the same filename as the TIFF but with a .jpg extension.
    quality : int, optional
        JPEG output quality, from 1 to 100.

    Returns
    -------
    pathlib.Path
        Path to the saved JPEG file.
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
    Tile a JPEG preview image and create metadata linking each tile to the original TIFF.

    The function divides a JPEG preview image into a user-defined number of rows and
    columns. Each tile is saved as a JPEG image. Metadata is also created to record
    the tile row, column, JPEG pixel bounds, TIFF pixel bounds, and scaling between
    the JPEG preview and the original TIFF image.

    Parameters
    ----------
    jpeg_path : str or pathlib.Path
        Path to the JPEG preview image.
    tiff_path : str or pathlib.Path
        Path to the original TIFF image from which the preview was created.
    rows : int
        Number of tile rows.
    cols : int
        Number of tile columns.
    output_dir : str or pathlib.Path
        Directory where the image tiles and metadata JSON file will be saved.
    prefix : str, optional
        Prefix used for output tile filenames. If None, the JPEG filename stem is used.
    quality : int, optional
        JPEG output quality for the saved tiles, from 1 to 100.

    Returns
    -------
    dict
        Metadata dictionary containing the source image paths, image sizes, scale
        factors, and per-tile JPEG and TIFF pixel bounds.
    """
    jpeg_path = Path(jpeg_path)
    tiff_path = Path(tiff_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if prefix is None:
        prefix = jpeg_path.stem

    current_timestamp = datetime.now().strftime("%H%M%S")

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

                tile_name = f"{prefix}_r{row + 1}_c{col + 1}_{current_timestamp}.jpg"
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
    Clear the folder containing generated image tiles.

    The function deletes the existing tile output folder, recreates it, and clears
    the selected tile from Streamlit session state if it exists. This is useful when
    the user changes the number of tile rows or columns.

    Parameters
    ----------
    tiles_output_path : str or pathlib.Path
        Path to the folder containing generated image tiles.

    Returns
    -------
    None
        The folder is cleared and recreated in place.
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
    List JPEG image files in a folder.

    The function scans the given folder and returns full paths to all regular
    with a .jpg extension. It is used to collect generated image tiles for display
    in the Streamlit image selection widget.

    Parameters
    ----------
    folder_path : str or pathlib.Path
        Path to the folder to search.

    Returns
    -------
    list of str
        List of full file paths to .jpg images found in the folder. If the folder
        does not exist or no JPEG files are found, an empty list is returned.
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

def tile_to_tiff_bounds_from_selected_image(metadata, user_selected_image_path):
    """
    Return original TIFF pixel bounds for a selected JPEG tile.

    The function extracts the row and column number from the selected tile filename,
    then searches the tile metadata to find the matching TIFF pixel bounds.

    Parameters
    ----------
    metadata : dict
        Metadata dictionary created by tile_jpeg_preview_with_metadata().
    user_selected_image_path : str or pathlib.Path
        Path to the selected JPEG tile. The filename must contain row and column
        information in the format _r<row>_c<col>.

    Returns
    -------
    dict
        Dictionary containing the selected tile bounds in original TIFF pixel
        coordinates. The dictionary includes left, top, right, bottom, width, and height.
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
    Convert a crop drawn on the full JPEG preview into original TIFF pixel bounds.

    The function uses the scale factors stored in the metadata to convert crop
    coordinates from the JPEG preview coordinate system to the original TIFF pixel
    coordinate system.

    Parameters
    ----------
    metadata : dict
        Metadata dictionary containing scale factors between the JPEG preview and
        original TIFF image.
    crop_x : int or float
        X-coordinate of the crop origin on the JPEG preview.
    crop_y : int or float
        Y-coordinate of the crop origin on the JPEG preview.
    crop_width : int or float
        Width of the crop on the JPEG preview.
    crop_height : int or float
        Height of the crop on the JPEG preview.

    Returns
    -------
    dict
        Dictionary containing the crop bounds in original TIFF pixel coordinates.
        The dictionary includes left, top, right, bottom, width, and height.
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
    Crop a TIFF image using pixel bounds.

    The function reads a window from the input TIFF based on the supplied pixel
    bounds and writes the cropped raster to a new TIFF file while preserving the
    correct geospatial transform.

    Parameters
    ----------
    tiff_path : str or pathlib.Path
        Path to the input TIFF image.
    output_path : str or pathlib.Path
        Path where the cropped TIFF should be saved.
    bounds : dict
        Pixel bounds used for cropping. Must contain left, top, width, and height.
    overwrite : bool, optional
        If False and output_path already exists, a FileExistsError is raised.
        If True, an existing output file may be overwritten.

    Returns
    -------
    pathlib.Path
        Path to the saved cropped TIFF file.
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