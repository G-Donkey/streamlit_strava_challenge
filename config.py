import osmnx as ox
import rasterio
import multiprocessing as mp
import pandas as pd
import numpy as np # For np.nan if needed

# For plotting (interactive and potentially static fallback)
import matplotlib.pyplot as plt 
# Note: folium and mapclassify are used by .explore() but not directly imported here usually.

# --- Configuration ---
PLACE_NAME = "Leuven, Belgium"
NETWORK_TYPE = "all_public"  # e.g., "drive", "walk", "bike", "all_public"
RASTER_FILE_PATH = "../DTM_20m.tif"  # Ensure this path is correct
RASTER_BAND = 1
NUM_CPUS = min(mp.cpu_count(), 4)  # Use up to 4 CPUs

# Visualization parameters for steepness
STEEPNESS_COLUMN_NAME = 'grade_abs_pct' # The attribute name for steepness in percent
VIS_MIN_STEEPNESS_PCT = 0.0  # Min value for the color scale (0%)
VIS_MAX_STEEPNESS_PCT = 20.0 # Max value for the color scale (20%)
VIS_COLORMAP = 'YlOrRd'      # Colormap for steepness