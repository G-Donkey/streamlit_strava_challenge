def calculate_percent_steepness(graph_with_grades):
    """
    Adds 'grade_abs_pct' (absolute grade in percent) to each edge in the graph.
    Modifies the graph in place.
    """
    print("Calculating steepness in percent...")
    for u, v, k, data in graph_with_grades.edges(keys=True, data=True):
        if 'grade_abs' in data and data['grade_abs'] is not None:
            data[STEEPNESS_COLUMN_NAME] = data['grade_abs'] * 100.0
        else:
            data[STEEPNESS_COLUMN_NAME] = None # or np.nan
    return graph_with_grades

def download_and_process_graph_data(place_name, network_type, raster_path, band, cpus):
    """
    Downloads a street network, reprojects it, adds elevation data,
    calculates edge grades, and converts absolute grade to percentage.
    """
    print(f"Starting data processing for: {place_name}")

    # 1. Get raster CRS
    try:
        with rasterio.open(raster_path) as src:
            raster_crs = src.crs
        print(f"Successfully read raster CRS: {raster_crs}")
    except rasterio.errors.RasterioIOError as e:
        print(f"Error opening raster file {raster_path}: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while reading raster CRS: {e}")
        return None

    # 2. Download graph in WGS84
    print("Downloading graph...")
    try:
        graph_wgs84 = ox.graph_from_place(
            place_name,
            network_type=network_type,
            retain_all=True,
            truncate_by_edge=True
        )
        print("Graph downloaded.")
    except Exception as e:
        print(f"Error downloading graph for {place_name}: {e}")
        return None

    # 3. Reproject graph to match raster CRS
    print(f"Reprojecting graph to CRS: {raster_crs}...")
    graph_projected = ox.project_graph(graph_wgs84, to_crs=raster_crs)
    print("Graph reprojected.")

    # 4. Add node elevations from the DTM
    print(f"Adding node elevations using {cpus} CPUs...")
    graph_with_elevation = ox.elevation.add_node_elevations_raster(
        graph_projected, raster_path, band=band, cpus=cpus
    )
    print("Node elevations added.")

    # 5. Calculate edge grades
    print("Calculating edge grades (absolute values)...")
    graph_with_grades = ox.elevation.add_edge_grades(
        graph_with_elevation, add_absolute=True
    )
    print("Edge grades calculated.")

    # 6. Convert steepness to percentage
    graph_with_percent_steepness = calculate_percent_steepness(graph_with_grades)
    
    print("Data processing complete.")
    return graph_with_percent_steepness


def create_interactive_steepness_map(graph, place_name_full, grade_column, vis_min_pct, vis_max_pct, cmap):
    """
    Generates and saves an interactive HTML map with edges colored by steepness.
    """
    print(f"Generating interactive map for '{place_name_full}' using column '{grade_column}'...")
    
    place_name_short = place_name_full.split(',')[0].replace(' ', '_')

    try:
        gdf_edges = ox.convert.graph_to_gdfs(graph, nodes=False, fill_edge_geometry=True)
    except Exception as e:
        print(f"Error converting graph to GeoDataFrame: {e}")
        return

    if gdf_edges.empty:
        print("Graph has no edges to visualize.")
        return

    if grade_column not in gdf_edges.columns or not gdf_edges[grade_column].notna().any():
        print(f"Warning: Column '{grade_column}' for steepness not found or has no valid data in GeoDataFrame.")
        print("Attempting to display a basic interactive map without steepness coloring.")
        try:
            m_basic = gdf_edges.explore(tooltip=['length', 'name'], style_kwds=dict(weight=2))
            output_filename_basic = f"interactive_map_no_grades_{place_name_short}.html"
            m_basic.save(output_filename_basic)
            print(f"\nBasic interactive map (no grade colors) saved to: {output_filename_basic}")
        except Exception as e_basic:
            print(f"Error generating basic interactive map: {e_basic}")
        return

    # Ensure the grade column is numeric for explore()
    gdf_edges[grade_column] = pd.to_numeric(gdf_edges[grade_column], errors='coerce')

    print(f"Visualizing {len(gdf_edges)} edges. Color scale for '{grade_column}': {vis_min_pct}% - {vis_max_pct}%.")

    try:
        # Using vmin and vmax to set the color scale range directly
        # scheme=None is implied when vmin/vmax are used for continuous data.
        m = gdf_edges.explore(
            column=grade_column,
            cmap=cmap,
            legend=True,
            tooltip=[grade_column, 'length', 'name', 'osmid'], # Added osmid for more info
            vmin=vis_min_pct,
            vmax=vis_max_pct,
            missing_kwds={
                "color": "lightgrey", # Color for edges with no steepness data
                "label": f"No data / Outside {vis_min_pct}-{vis_max_pct}%",
            },
            # k=7, # Number of classes, typically for 'scheme'. For vmin/vmax, often implies continuous legend.
            style_kwds=dict(weight=3), # Line thickness
            legend_kwds=dict(caption=f"Steepness ({vis_min_pct}% to {vis_max_pct}%)") # Legend title
        )
        
        output_filename = f"interactive_steepness_map_{place_name_short}_0_to_20_pct.html"
        m.save(output_filename)
        print(f"\nInteractive map saved to: {output_filename}")
        print(f"Please open '{output_filename}' in a web browser to view the map.")

    except Exception as e:
        print(f"Error during interactive map generation or saving: {e}")
        print("Please ensure 'folium' and 'mapclassify' are installed (e.g., 'pip install folium mapclassify').")


import numpy as np # For np.nan if data is missing

# Your provided physiological model functions:
def cot_adj(i):
    """
    Adjusted Minetti Cost of Transport (COT) for grade i (decimal).
    Valid for -0.45 <= i <= +0.45.  At i=0, COT_adj(0) = 4.02 J·kg^-1·m^-1 (ACSM flat cost).
    """
    return (
        155.4 * i**5
      - 30.4  * i**4
      - 43.3  * i**3
      + 46.3  * i**2
      + 19.5  * i
      + 4.02
    )

def estimate_run_time_allgrades(L_m, VO2max, effort, grade):
    """
    Estimate running time (minutes) to cover an edge of length L_m (m)
    at given effort (1-5) and grade (decimal, -0.45 <= grade <= +0.45),
    using net VO2 (ml/kg/min) and adjusted Minetti COT.
    """
    # 1. Effort -> VO2 fraction (midpoints)
    f_map = {1: 0.575, 2: 0.730, 3: 0.840, 4: 0.905, 5: 0.970}
    fe = f_map.get(effort)
    if fe is None:
        raise ValueError("Effort must be an integer between 1 and 5.")
    
    # 2. Net VO2 (ml·kg^-1·min^-1)
    VO2_net = VO2max * fe - 3.5
    if VO2_net <= 0:
        # This implies the effort level is too low for sustained activity above resting,
        # or VO2max is very low. Could result in very slow/infinite time.
        raise ValueError(f"VO2max ({VO2max}) * f_e ({fe}) must exceed 3.5 (resting VO2). Resulted in VO2_net: {VO2_net:.2f}")
    
    # 3. Adjusted COT (J·kg^-1·m^-1)
    if not -0.45 <= grade <= 0.45: # Check grade bounds
        raise ValueError(f"Grade {grade:.3f} out of valid range [-0.45, +0.45].")
    COT = cot_adj(grade)
    if COT <= 0: # Should not happen for valid grades with Minetti's polynomial
        raise ValueError(f"Computed COT_adj ({COT:.2f}) is non-positive; check polynomial or grade {grade:.3f}.")
    
    # 4. Running speed (m/min)
    speed_m_per_min = (VO2_net * 20.1) / COT
    if speed_m_per_min <= 0 : # Speed must be positive to cover distance
        # This could happen if COT is extremely high (very steep adverse grade)
        # or VO2_net is very low relative to COT.
        raise ValueError(f"Calculated speed ({speed_m_per_min:.2f} m/min) is non-positive. Check inputs or model applicability for this grade/effort.")

    # 5. Time (min)
    time_min = L_m / speed_m_per_min
    return time_min

# Modified function to add metrics to edges
def add_formula_metrics_to_edges(graph, vo2max_user, effort_user):
    """
    Adds edge attributes relevant to the optimization formula using physiological time estimation:
    - 'dist_km_edge': distance in kilometers.
    - 'time_min_edge': estimated time in minutes for the edge (using estimate_run_time_allgrades).
    - 'elev_gain_edge': elevation gain in meters for the edge.
    - 'merit_edge': the positive score contribution of this edge.
      (Score = 1.1*dist_km + 0.11*time_min + 0.02*elev_gain_m)

    Modifies the input 'graph' in place.
    Assumes 'graph' has 'length' (meters) and 'grade' (decimal) on edges, 
    and 'elevation' (meters) on nodes.
    """
    if not graph or not graph.nodes or not graph.edges:
        print("Error: Graph is empty or invalid. Cannot add metrics.")
        return graph

    for u, v, k, data in graph.edges(keys=True, data=True):
        dist_m = data.get('length')
        edge_grade = data.get('grade') # Signed grade (rise/run)

        if dist_m is None or edge_grade is None:
            data['dist_km_edge'] = np.nan
            data['time_min_edge'] = np.nan
            data['elev_gain_edge'] = np.nan
            data['merit_edge'] = np.nan
            continue

        # 1. Distance in kilometers for the edge
        dist_km = dist_m / 1000.0
        data['dist_km_edge'] = dist_km

        # 2. Estimated time in minutes for the edge (using new model)
        time_min_on_edge = np.nan # Default to NaN if calculation fails
        try:
            # Ensure grade is within the model's typical input range if necessary,
            # estimate_run_time_allgrades already clips/checks grade internally.
            time_min_on_edge = estimate_run_time_allgrades(dist_m, vo2max_user, effort_user, edge_grade)
        except ValueError as e:
            # Silently set to NaN for minimalism, or print a warning if preferred for debugging
            # print(f"Warning: Could not calculate time for edge ({u}-{v}-{k}) grade {edge_grade:.3f}: {e}")
            pass # Keep it minimal, time_min_on_edge remains NaN
        data['time_min_edge'] = time_min_on_edge
        
        # 3. Elevation gain in meters for the edge
        elev_gain_on_edge = 0.0
        node_u_attrs = graph.nodes.get(u, {})
        node_v_attrs = graph.nodes.get(v, {})
        node_u_elev = node_u_attrs.get('elevation')
        node_v_elev = node_v_attrs.get('elevation')
        
        if node_u_elev is not None and node_v_elev is not None:
            elevation_difference = node_v_elev - node_u_elev
            if elevation_difference > 0:
                elev_gain_on_edge = elevation_difference
        data['elev_gain_edge'] = elev_gain_on_edge
        
        # 4. "Merit" of the edge
        # Only calculate if time_min_on_edge is a valid number
        if pd.notna(time_min_on_edge): # Check if time_min_on_edge is not NaN
            edge_merit_score = (1.1 * dist_km) + \
                               (0.11 * time_min_on_edge) + \
                               (0.02 * elev_gain_on_edge)
            data['merit_edge'] = edge_merit_score
        else:
            data['merit_edge'] = np.nan # If time couldn't be calculated, merit is also undefined
            
    return graph

# --- How to use it with your existing graph 'G' ---
# # 1. Ensure your graph 'G' is loaded and has the necessary base attributes:
# #    - Edges: 'length' (meters), 'grade' (decimal, e.g., 0.05 for 5%)
# #    - Nodes: 'elevation' (meters)
# #    (Your graph data seems to have these based on the column lists you provided)

# # 2. Define user-specific physiological parameters:
# my_vo2max = 45.0  # Example VO2max (ml/kg/min), replace with actual value
# my_effort_level = 3 # Example effort level (1-5), replace with actual value

# # 3. Call the function to add the new metrics to your graph G:
# # G = add_formula_metrics_to_edges(G, vo2max_user=my_vo2max, effort_user=my_effort_level)

# # 4. Verify by checking a sample edge:
# # if G and G.edges:
# #     # Filter for an edge where time calculation might be interesting (e.g., non-zero grade)
# #     sample_edge_info = None
# #     for u_s, v_s, k_s, data_s in G.edges(data=True, keys=True):
# #         if pd.notna(data_s.get('grade')) and data_s['grade'] != 0:
# #             sample_edge_info = (u_s, v_s, k_s, data_s)
# #             break
# #     if not sample_edge_info: # Fallback to first edge
# #          sample_edge_info = list(G.edges(data=True, keys=True))[0]
    
# #     u, v, k, data = sample_edge_info
# #     print(f"Sample edge ({u}-{v}-{k}) data with new metrics (VO2max={my_vo2max}, Effort={my_effort_level}):")
# #     print(f"  Input grade: {data.get('grade')}")
# #     print(f"  Input length (m): {data.get('length')}")
# #     for attr in ['dist_km_edge', 'time_min_edge', 'elev_gain_edge', 'merit_edge']:
# #         print(f"  {attr}: {data.get(attr)}")
# # else:
# #     print("Graph G is not defined or has no edges for sample check.")