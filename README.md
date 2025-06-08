# 🏃‍♂️ Strava Challenge Route Analyzer

This application analyzes street and trail networks for a given location to identify ideal routes for running or walking based on physiological models and user-defined preferences. It calculates various metrics for each segment in the network—such as steepness, estimated time, and a custom "merit score"—and visualizes the results on an interactive map.

The front-end is built with Streamlit, allowing users to dynamically configure parameters and generate new map visualizations on the fly.

## ✨ Features

  * **Dynamic Network Analysis**: Fetches street/trail data for any location from OpenStreetMap using the `osmnx` library.
  * **Elevation-Aware**: Integrates a local Digital Terrain Model (DTM) raster file to add elevation data to the network's nodes.
  * **Physiological Modeling**: Estimates the time to traverse each segment based on user-provided VO₂max and effort level.
  * **Custom Merit Score**: Calculates a unique "merit score" for each segment to quantify its value for a challenge, factoring in distance, time, and elevation gain.
  * **Interactive Visualization**: Generates and displays an interactive map where segments are color-coded by a selected attribute (e.g., Merit per Minute, Steepness). The app uses `folium` to create these visualizations.
  * **Web-Based UI**: A simple and intuitive user interface powered by Streamlit for configuration and display.

## ⚙️ How It Works

The application follows a multi-stage data processing pipeline, orchestrated by the main Streamlit app (`app.py`).

*A simplified diagram of the application's data flow.*

1.  **Input Configuration (`app.py`)**:
    The user provides inputs via the Streamlit sidebar:

      * **Place Name**: The location to analyze (e.g., "Leuven, Belgium").
      * **Network Type**: The type of network to download from OSMnx (e.g., `all_public`, `walk`).
      * **Attribute to Visualize**: The metric to use for color-coding the map.
      * **VO₂max & Heart Rate Zone**: Personal fitness parameters used in the physiological model.

2.  **Graph Processing (`graph_processing.py`)**:
    When the "Generate Map" button is clicked, this module:

      * Downloads the specified graph data from OpenStreetMap using `osmnx.graph_from_place`.
      * Opens a local Digital Terrain Model (DTM) raster file to get its Coordinate Reference System (CRS).
      * Re-projects the graph to match the raster's CRS, ensuring spatial alignment.
      * Adds elevation data from the DTM to every node (intersection) in the graph using `osmnx.elevation.add_node_elevations_raster`.
      * Calculates the grade (slope) for every edge (street/path segment) based on the elevation change and length.
      * Creates an absolute steepness column in percent (`grade_abs_pct`) by multiplying the absolute grade by 100.

3.  **Metric Calculation (`metric_calculation.py`)**:
    The graph, now enriched with elevation and grade data, is passed to this module. For every edge, it calculates:

      * **Estimated Time (`time_min_edge`)**: Uses the `physiological_model.py` to estimate the time (in minutes) a user would take to run the segment.
      * **Elevation Gain (`elev_gain_edge`)**: The positive elevation change along the edge.
      * **Merit Score (`merit_edge`)**: A custom-defined score calculated as a weighted sum of distance, time, and elevation gain.
      * **Merit per Minute (`merit_edge_per_minute`)**: The merit score normalized by the estimated time, highlighting efficient segments for scoring points.

4.  **Map Visualization (`visualization.py`)**:
    The final, fully enriched graph is used to generate the map:

      * The graph is converted into a GeoDataFrame using `osmnx.convert.graph_to_gdfs`.
      * An interactive map is created using `folium` (via the `.explore()` method of GeoPandas).
      * Edges are color-coded based on the user's selected attribute.
      * For steepness (`grade_abs_pct`), a fixed legend range of 0-15% is used for better visual consistency.
      * The map is saved as a standalone HTML file.

5.  **Display (`app.py`)**:
    The main app reads the generated HTML file and displays the interactive map in the Streamlit interface using `st.components.v1.html`.

## 💨 Physiological Modeling Deep Dive

A core feature of this application is its ability to estimate the time required to run along any given segment of the network. This is achieved by a physiological model in `physiological_model.py` that considers the user's fitness, their chosen effort level, and the terrain's steepness.

### Key Concepts

1.  **User Fitness (VO₂max and Effort)**
    The model is personalized based on two parameters:

      * **VO₂max**: The user's maximal oxygen consumption (`ml/kg/min`), which is a primary indicator of cardiovascular fitness.
      * **Effort Level**: A scale from 1 to 5 representing the user's intended exertion. This is mapped to a specific fraction of their VO₂max via the `f_map` dictionary. For example, an effort of '3' corresponds to using 84% of one's VO₂max.

    The model first calculates the **Net VO₂**, which is the oxygen available for exercise after subtracting the body's resting oxygen requirement (assumed to be 3.5 ml/kg/min):
    `VO2_net = VO2max * f_map.get(effort) - 3.5`.

2.  **Energy Cost of Running (Cost of Transport - COT)**
    To calculate speed, the model must know the energy required to run on a specific slope. This is quantified by the **Cost of Transport (COT)**, which is the energy cost to move a unit of body mass over a unit of distance. The model implements a function `cot_adj(i)` based on an adjusted version of Minetti's 2002 model for running on graded terrain. This function is a 5th-degree polynomial that takes the grade `i` (as a decimal) and returns the corresponding COT.
    `cot = 155.4*i⁵ - 30.4*i⁴ - 43.3*i³ + 46.3*i² + 19.5*i + 4.02`.

3.  **From Energy to Speed**
    With the available oxygen (`VO2_net`) and the energy cost (`COT`), the model calculates the running speed in meters per minute. The formula converts oxygen consumption into mechanical power to determine running speed:
    `speed_m_per_min = (VO2_net * 20.1) / COT`.

4.  **Final Time Calculation**
    Once the speed for a segment is known, the time to traverse it is a simple calculation:
    `time_minutes = distance_meters / speed_m_per_min`.

### Workflow and Error Handling

The `metric_calculation.py` script orchestrates this process for every edge in the graph.

1.  For an edge, it retrieves the length (`dist_m`) and grade (`edge_grade`).
2.  It calls `estimate_run_time_allgrades` with these values and the user's fitness data.
3.  The model performs several checks to ensure the inputs are valid:
      * Is the effort level between 1 and 5?
      * Is the grade within the model's valid range (-0.45 to +0.45)?
      * Is the calculated Net VO₂, COT, and speed positive?
4.  If any check fails, the function raises a `ValueError`. The calling script in `metric_calculation.py` catches this error and assigns `np.nan` as the edge's time. This robustly handles segments where the model is not applicable (e.g., extremely steep slopes) without crashing the application.
5.  If successful, the calculated time is returned and stored as the `time_min_edge` attribute for that edge.

## 🛠️ Setup and Installation

### Prerequisites

  * Python 3.8+
  * A Digital Terrain Model (DTM) raster file (e.g., in GeoTIFF format).

### 1\. Data File

You must provide your own DTM file, download it from here for Belgium: https://ac.ngi.be/remoteclient-open/ngi-standard-open/Rasterdata/DTM_20m/6657e6da-7345-416f-bef6-c6a8b2def9bd_tiff_3812.zip.

  * Place the file in the root directory of the project.
  * Update the `RASTER_FILE_PATH` variable in `app.py` to match its filename (e.g., `"./DTM_20m.tif"`).

### 2\. Python Packages

Install the required packages using pip. You can create a `requirements.txt` file with the content below and run `pip install -r requirements.txt`.

**`requirements.txt`:**

```
streamlit
pandas
numpy
osmnx
rasterio
geopandas
folium
mapclassify
```

## 🚀 How to Run

1.  Ensure your DTM file is in the project directory and its path in `app.py` is correct.
2.  Open your terminal or command prompt.
3.  Navigate to the project's root directory.
4.  Run the following command:
    ```bash
    streamlit run app.py
    ```
5.  Your web browser should open with the Streamlit application. Configure the options in the sidebar and click "Generate and Display Map".

## 📂 Code Structure

  * **`app.py`**: The main application file. It defines the Streamlit user interface, orchestrates the workflow, and displays the final map. All user-configurable parameters are set here.
  * **`graph_processing.py`**: Handles downloading the graph from OSM, reprojecting it, and adding elevation and grade data from the raster file.
  * **`metric_calculation.py`**: Calculates physiological and challenge-specific metrics for each edge in the graph, such as time, merit score, and merit per minute.
  * **`physiological_model.py`**: Contains the scientific model for estimating running speed based on VO₂max, effort, and grade.
  * **`visualization.py`**: Takes the final graph and generates the interactive HTML map, handling data visualization, legends, and tooltips.
  * **`config.py`** (Legacy): This file exists but is no longer used by `app.py`. All its parameters have been moved into the Streamlit sidebar to allow for dynamic user configuration.