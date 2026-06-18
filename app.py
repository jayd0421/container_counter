import os
from PIL import Image
import streamlit as st
from streamlit_image_select import image_select

import scripts.subset_image as si
import scripts.count_containers as cc

st.set_page_config(
   page_title="Container Counter App",
)

Image.MAX_IMAGE_PIXELS = None

os.makedirs("outputs/preview_tiles", exist_ok=True)

CONTAINER_HEIGHT = 2.6
PREVIEW_IMAGE_PATH = "outputs/preview_image.jpg"
USER_SELECTED_AOI_PATH = "outputs/preview_tiles/user_cropped_aoi_image.tif"
CONTAINER_SEGMENT_GEOJSON_PATH = "outputs/preview_tiles/container_segements.geojson"
FILTERED_LAS_PATH = "outputs/preview_tiles/filtered_las.las"
CROPPED_DSM_PATH = "outputs/preview_tiles/cropped_dsm.tif"
TILES_OUTPUT_PATH = "outputs/preview_tiles"
SAM_MODEL_PATH = "models/sam_vit_b_01ec64.pth"

# --- Session state defaults ---
if "page" not in st.session_state:
    st.session_state.page = "subset"
if "tiff_crop_bounds" not in st.session_state:
    st.session_state.tiff_crop_bounds = None
if "user_selected_image_path" not in st.session_state:
    st.session_state.user_selected_image_path = None

# ── SUBSET PAGE ────────────────────────────────────────────────────────────────
if st.session_state.page == "subset":
    title_col, layout_col = st.columns([3, 1])
    with title_col:
        st.title("Container Counter App")
    with layout_col:
        st.space("medium")
        if st.toggle("Wide layout"):
            st.set_page_config(layout="wide")

    file_paths_correct = 0

    rgb_tiff_file_path_col, las_file_path_col, dsm_tiff_file_path_col, image_subset_method_col, image_tiles_col = st.columns([2.5, 2, 2.5, 2, 3.5])

    with rgb_tiff_file_path_col:
        RGB_TIFF_PATH = st.text_input("Path to RGB tiff file:", key="rgb_path")
        if RGB_TIFF_PATH == "":
            pass
        elif RGB_TIFF_PATH.split(".")[-1] not in ("tif", "tiff"):
            st.error("Incorrect file extension")
        else:
            file_paths_correct += 1

    with las_file_path_col:
        LAS_PATH = st.text_input("Path to LAS file:", key="las_path")
        if LAS_PATH == "":
            pass
        elif LAS_PATH.split(".")[-1] != "las":
            st.error("Incorrect file extension")
        else:
            file_paths_correct += 1

    with dsm_tiff_file_path_col:
        DSM_TIFF_PATH = st.text_input("Path to DSM tiff file:", key="dsm_path")
        if DSM_TIFF_PATH == "":
            pass
        elif DSM_TIFF_PATH.split(".")[-1] not in ("tif", "tiff"):
            st.error("Incorrect file extension")
        else:
            file_paths_correct += 1

    if file_paths_correct == 3:
        si.tiff_to_jpeg(RGB_TIFF_PATH, PREVIEW_IMAGE_PATH)

        with image_subset_method_col:
            image_subset_method = st.radio("Subset method", ["BBOX", "Tiles"], key="subset", horizontal=True)

        if image_subset_method == "BBOX":
            st.warning("This option is not available yet. Select Tiles.")
            st.image(PREVIEW_IMAGE_PATH)

        elif image_subset_method == "Tiles":
            with st.spinner(text="Tiling the imagery...", show_time=True, width="content"):
                with image_tiles_col:
                    rows_col, cols_col = st.columns([1, 1])
                    with rows_col:
                        n_rows = st.number_input(
                            "Tile rows", 
                            value=4, min_value=2, max_value=10, key="rows",
                            on_change=si.clear_tiles_output_folder(TILES_OUTPUT_PATH)
                            )
                    
                    with cols_col:
                        n_cols = st.number_input(
                            "Tile columns", 
                            value=4, min_value=2, max_value=10, key="cols",
                            on_change=si.clear_tiles_output_folder(TILES_OUTPUT_PATH)
                            )
                        
                metadata = si.tile_jpeg_preview_with_metadata(
                    jpeg_path=PREVIEW_IMAGE_PATH,
                    tiff_path=RGB_TIFF_PATH,
                    rows=n_rows,
                    cols=n_cols,
                    output_dir=TILES_OUTPUT_PATH,
                )

                chip_images_list = si.list_files_in_folder(TILES_OUTPUT_PATH)
                user_selected_image_path = image_select(
                    "Select image tile", chip_images_list, use_container_width=True
                )

                with st.expander("Preview selected image"):
                    st.image(user_selected_image_path)

                tiff_crop_bounds = si.tile_to_tiff_bounds_from_selected_image(
                    metadata=metadata,
                    user_selected_image_path=user_selected_image_path,
                )
                si.crop_tiff_using_bounds(
                    tiff_path=RGB_TIFF_PATH,
                    output_path=USER_SELECTED_AOI_PATH,
                    bounds=tiff_crop_bounds,
                )

            # ── Button that navigates to the count page ──
            if st.button("Start container count", type="primary"):
                st.session_state.tiff_crop_bounds = tiff_crop_bounds
                st.session_state.user_selected_image_path = user_selected_image_path
                st.session_state.nav_las_path = LAS_PATH
                st.session_state.nav_rgb_path = RGB_TIFF_PATH
                st.session_state.nav_dsm_path = DSM_TIFF_PATH
                st.session_state.page = "count"
                st.rerun()

# ── COUNT PAGE ─────────────────────────────────────────────────────────────────
elif st.session_state.page == "count":
    st.title("Container Counter App")

    if st.button("← Back to subset"):
        st.session_state.page = "subset"
        st.rerun()

    tiff_crop_bounds = st.session_state.tiff_crop_bounds
    user_selected_image_path = st.session_state.user_selected_image_path
    LAS_PATH = st.session_state.nav_las_path
    RGB_TIFF_PATH = st.session_state.nav_rgb_path
    DSM_TIFF_PATH = st.session_state.nav_dsm_path

    with st.spinner(text="Generating container masks...", show_time=True, width="content"):
        masks = cc.generate_container_segment_masks(user_selected_image_path, SAM_MODEL_PATH)
        boxes = cc.convert_masks_to_boxes(masks)
        cc.convert_boxes_to_geojson(boxes, USER_SELECTED_AOI_PATH, CONTAINER_SEGMENT_GEOJSON_PATH)

    with st.spinner(text="Getting container elevations from LIDAR data...", show_time=True, width="content"):
        map_bounds = cc.pixel_bounds_to_map_bounds(RGB_TIFF_PATH, tiff_crop_bounds)
        filtered_las_path = cc.filter_las_by_map_bounds(LAS_PATH, FILTERED_LAS_PATH, map_bounds)
        container_boxes_gdf = cc.add_las_elevation_stats(CONTAINER_SEGMENT_GEOJSON_PATH, filtered_las_path)
        cropped_dsm_path = cc.crop_dsm_by_map_bounds(DSM_TIFF_PATH, CROPPED_DSM_PATH, map_bounds)
        container_boxes_gdf = cc.add_dsm_elevation_stats(container_boxes_gdf, cropped_dsm_path)

    with st.spinner(text="Cleaning container segments...", show_time=True, width="content"):
        filtered_container_boxes_gdf = cc.filter_clean_container_boxes_gdf(container_boxes_gdf)
        filtered_container_boxes_gdf = cc.add_color_to_containers(USER_SELECTED_AOI_PATH, filtered_container_boxes_gdf)
        filtered_container_boxes_gdf["n_containers"] = round(filtered_container_boxes_gdf["elev"] / CONTAINER_HEIGHT, 0)
        n_containers = int(filtered_container_boxes_gdf.n_containers.sum())

        n_stacks_col, n_containers_col = st.columns([1, 1])
        n_stacks_col.metric("Container Stacks", len(filtered_container_boxes_gdf), border=True)
        n_containers_col.metric("Containers", n_containers, border=True)

        with st.expander("View segmentation"):
            image_path = cc.plot_image(filtered_container_boxes_gdf, USER_SELECTED_AOI_PATH)
            st.image(image_path)

        cc.add_3d_visualisation(filtered_container_boxes_gdf)
