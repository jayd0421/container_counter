# Container Counter App

A Streamlit web application for estimating the number of shipping containers in high-resolution aerial imagery using image tiling, Segment Anything Model segmentation, LiDAR point-cloud elevation information, and DSM raster elevation statistics.

The app allows a user to:

* Load an RGB GeoTIFF image
* Load a corresponding LAS point cloud
* Load a corresponding DSM GeoTIFF
* Subset a large image using image tiles
* Segment likely container stacks using Segment Anything
* Estimate stack heights using LiDAR and DSM elevation information
* Estimate the number of containers in each stack
* View segmentation results and a 3D visualisation of detected container stacks

## App Preview

The app has two main tabs:

1. **Subset image**
   Used to select the input RGB TIFF, LAS file, DSM TIFF, and image tile.
   ![Subset Image](assets/preview1.png)
   
3. **Count containers**
   Used to run segmentation, calculate elevation-based container counts, and visualise the results.
   ![Count Containers](assets/preview2.png)

## Project Structure

```text
.
├── app.py
├── scripts/
│   ├── subset_image.py
│   └── count_containers.py
├── models/
│   └── sam_vit_b_01ec64.pth
├── requirements.txt
├── README.md
└── .gitignore
```

## Required Input Data

The app expects three input files:

```text
RGB GeoTIFF image: .tif or .tiff
LAS point cloud:   .las
DSM GeoTIFF:       .tif or .tiff
```

The RGB image, LAS point cloud, and DSM should cover the same area and should ideally be in the same coordinate reference system.

## Segment Anything Model Checkpoint

This app uses the [Segment Anything](https://github.com/facebookresearch/segment-anything/tree/main) ViT-B checkpoint: [ViT-B SAM model.](https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth)

The model checkpoint is not included in this repository because it is a large file.

Download the checkpoint from [here](https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth), then place it in the `models/` folder so that the final path is:

```text
models/sam_vit_b_01ec64.pth
```

Make sure the filename matches exactly.

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/YOUR-USERNAME/container-counter-app.git
cd container-counter-app
```

### 2. Create a Conda environment

```bash
conda create -n container-counter python=3.11 -y
```

Activate the environment:

```bash
conda activate container-counter
```

### 3. Install dependencies

Install the required Python packages:

```bash
pip install -r requirements.txt
```

Depending on your operating system, some geospatial libraries may install more reliably through Conda. If `rasterio`, `geopandas`, or related packages fail with `pip`, try:

```bash
conda install -c conda-forge rasterio geopandas shapely fiona pyproj -y
pip install -r requirements.txt
```

## Running the App

From the project root folder, run:

```bash
streamlit run app.py
```

This will start the Streamlit app and open it in your browser.

If it does not open automatically, copy the local URL shown in the terminal, usually something like:

```text
http://localhost:8501
```

## How to Use the App

### Step 1: Open the app

Run:

```bash
streamlit run app.py
```

### Step 2: Provide input file paths

In the **Subset image** tab, enter paths to:

```text
RGB TIFF file
LAS file
DSM TIFF file
```

Example:

```text
data/rgb_image.tif
data/point_cloud.las
data/dsm.tif
```

### Step 3: Choose the subset method

Currently, the main available subset method is:

```text
Tiles
```

The app converts the RGB TIFF into a JPEG preview, divides it into rows and columns, and allows the user to select one tile.

### Step 4: Set tile rows and columns

Choose the number of tile rows and tile columns.

For example:

```text
Tile rows:    4
Tile columns: 4
```

The app will generate image tiles and display them in a selectable grid.

### Step 5: Select an image tile

Click one of the displayed tiles.

The selected tile is mapped back to the original TIFF pixel coordinates using metadata generated during tiling.

### Step 6: Start container counting

Activate:

```text
Start container count
```

Then go to the **Count containers** tab.

The app will:

1. Generate segmentation masks using Segment Anything
2. Convert masks to rotated bounding boxes
3. Convert bounding boxes to GeoJSON polygons
4. Filter the LAS point cloud to the selected image bounds
5. Crop the DSM to the same selected image bounds
6. Add LiDAR and DSM elevation statistics to each detected polygon
7. Estimate the number of container stacks and containers
8. Display a 3D visualisation

## Outputs

The app writes temporary and generated outputs to the `outputs/` folder.

Typical generated outputs include:

```text
outputs/preview_image.jpg
outputs/preview_tiles/
outputs/preview_tiles/user_cropped_aoi_image.tif
outputs/preview_tiles/container_segements.geojson
outputs/preview_tiles/filtered_las.las
outputs/preview_tiles/cropped_dsm.tif
```

These outputs are generated automatically when the app runs.

## Important Notes

### Coordinate Reference System

The RGB TIFF, DSM TIFF, and LAS point cloud should be in the same coordinate reference system. If they are not, the point-cloud filtering and DSM-based elevation statistics may not align correctly with the selected image tile.

### Model Checkpoint

The app expects the [SAM checkpoint](https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth) at:

```text
models/sam_vit_b_01ec64.pth
```

If the checkpoint is missing, the segmentation step will fail.

### GPU Support

The app uses PyTorch and Segment Anything. If CUDA is available, the model can run on GPU. If CUDA is not available, it will run on CPU, but segmentation may be slower.

## Current Limitations

* The BBOX subset option is not yet implemented.
* The app currently relies on file paths entered by the user rather than file upload widgets.
* Results depend on the quality and alignment of the RGB TIFF, LAS point cloud, and DSM.
* The container count estimate assumes a standard container height of approximately 2.6 metres.
* Some filtering thresholds are currently hard-coded and adjustments are not yer implemented for different sites or datasets.

## Future Improvements

* Implementing the BBOX drawing workflow
* Adding CRS validation between RGB TIFF, DSM, and LAS inputs
* Adding user controls for container height and filtering thresholds
* Saving final results as GeoJSON, CSV, or GeoPackage
* A download button for outputs
* Better error messages when files are missing or misaligned

## License

```text
MIT License
```

## Author

Developed by Mary Muthee, Pedro Alfonso and Jedidiah Chibinga.
