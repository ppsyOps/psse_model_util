import warnings
from pathlib import Path
import sys
from typing import Dict

import pandas as pd

from psse_model_util.common.dirs import clear_site_cache, clear_cache, clear_user_cache
from psse_model_util.common.dirs import site_temp_dir
from psse_model_util.dataformat.classes import ModelDF
from psse_model_util.model import Model


def basic_example(raw_path: str | Path = None):
    # Load a model from a raw or rawx file.
    print('[[BASIC EXAMPLE]]')
    from psse_model_util.model import Model
    model = Model(file_path_or_json=raw_path,  # Path to the .raw or .rawx file
                  name='my_model',  # Give your model a convenient name.
                  force_recalculate=True)  # Do not use locally cached data.
    return model

def model_info_example(raw_path: str | Path = None):
    print('[[MODEL INFO EXAMPLE]]')
    model = Model(file_path_or_json=raw_path,  # Path to the .raw or .rawx file
                  name='my_model',  # Give your model a convenient name.
                  force_recalculate=True)  # Do not use locally cached data.

    print(f'model: {model.name}')

    # The source raw file
    print(f'model raw file: {model.raw_file_path}')

    # The model is automatically cached to disk.  This makes loading the model
    # in the future faster.
    print(f'model cache: {model.pickle_path}')

    # Optionally, export model data to csv files.
    print(f'model csv folder: {model.csv_folder}')
    model.to_csv()

    # Get a dict of model.network dataframes like model.network.bus,
    # model.network.generator, etc.  Data type: Dict[str, pd.DataFrame]
    network_dfs: Dict[str, pd.DataFrame] = model.network_dfs()
    print(f'model.network DataFrames: {network_dfs}')

    # Get a pd.DataFrame of bus data.
    print(f'model.network.bus:')
    print(model.network.bus.head())


def filter_model_inplace_example(raw_path: str | Path = None):
    """
    Example: Filters the model to a subset of areas.  This frees up memory and
    creates a smaller model, which can speed up computations that might take a
    lot of time.
    """
    print('[[FILTER INPLACE EXAMPLE]]')
    model = Model(file_path_or_json=raw_path,  # Path to the .raw or .rawx file
                  name='my_model',  # Give your model a convenient name.
                  force_recalculate=False)  # Do not use locally cached data.

    # Prebuilt sets of areas are available in psse_model_util.common.constants
    # These include: INCLUDE_AREAS, NATIVE_AREAS, NEIGHBOR_AREAS.
    # You can also create a custom dict like:{1: 'CENTRAL', 2: 'EAST', 3: 'CENTRAL_DC'}

    # Filter the model to a subset of areas in place.
    from psse_model_util.common.constants import INCLUDE_AREAS, NATIVE_AREAS, NEIGHBOR_AREAS
    print(f'Bus count before filtering: {len(model.network.bus)}')
    model.filter_by_area(areas=NATIVE_AREAS, inplace=True)
    print(f'Bus count after filtering: {len(model.network.bus)}')


def filtered_model_copy_example(raw_path: str | Path = None):
    print('[[FILTERED COPY EXAMPLE]]')
    model = Model(file_path_or_json=raw_path,  # Path to the .raw or .rawx file
                  name='my_model',  # Give your model a convenient name.
                  force_recalculate=False)  # Do not use locally cached data.
    """
    Example: create a copy of the model filtered to a subset of areas.  This
    takes more memory but also creates a smaller model, which can speed up
    computations that might take a lot of time.
    """
    # Prebuilt sets of areas are available in psse_model_util.common.constants
    # These include: INCLUDE_AREAS, NATIVE_AREAS, NEIGHBOR_AREAS.

    # Make a copy of the model that is filtered to a subset of areas.
    areas = {1: 'CENTRAL', 2: 'EAST', 3: 'CENTRAL_DC'}
    filtered_model = model.filter_by_area(areas=areas, inplace=False)


def cache_example(raw_path: str | Path = None):
    """
    Example: Models are automatically cached to disk.  You can delete the
    cached copy or set force_recalculate=False when creating a Model object.
    You can also maually write a new cache with the to_pickle method.
    """
    print('[[CACHE EXAMPLE]]')
    model = Model(file_path_or_json=raw_path,  # Path to the .raw or .rawx file
                  name='my_model',  # Give your model a convenient name.
                  force_recalculate=True)  # Use locally cached model if available.

    # The model is automatically cached to disk.  This makes loading the model
    # in the future faster.  If the cache file does not exist, it will be
    # created.
    print(f'model cache: {model.pickle_path}')

    # Delete the cache file for this specific model.
    model.pickle_path.unlink()

    # Create a new cache of the model.
    model.to_pickle()

    # Delete all cached models.
    from psse_model_util.common.dirs import clear_site_cache, clear_cache, clear_user_cache
    clear_cache()


def csv_export_example(raw_path: str | Path = None):
    """
    Example: The to_csv method exports each dataframe in Model.Network to its
    own csv file located at Model.csv_folder.  The folder is automatically set
    as a subdirectory of the raw file path, but you can change it if you wish.
    """
    print('[[CSV EXPORT EXAMPLE]]')
    model = Model(file_path_or_json=raw_path,  # Path to the .raw or .rawx file
                  name='my_model',  # Give your model a convenient name.
                  force_recalculate=False)  # Do not use locally cached data.

    # Filter the model inplace to a subset of areas.
    from psse_model_util.common.constants import INCLUDE_AREAS, NATIVE_AREAS, NEIGHBOR_AREAS
    model.filter_by_area(areas=NATIVE_AREAS, inplace=True)

    # Default CSV export location is a sub-folder of
    # the folder containing the raw file.
    print(f"CSV export folder (default): {model.csv_folder}")

    # Optionally, change the folder where csv files are exported.
    model.csv_folder = site_temp_dir / f'{model.name}_export'

    # Export Model.network DataFrames to CSV.
    model.to_csv()
    print(f"CSV files exported to: {model.csv_folder}")

    # Delete the csv files we just exported.
    try:
        model.csv_folder.unlink()
    except (FileNotFoundError, PermissionError):
        pass


def network_section_with_bus_info(raw_path: str | Path = None):
    """
    Example: Add bus information to a specific Model.network DataFrame.
    """
    print('[[NETWORK SECTION WITH BUS INFO EXAMPLE]]')
    model = Model(file_path_or_json=raw_path,  # Path to the .raw or .rawx file
                  name='my_model',  # Give your model a convenient name.
                  force_recalculate=False)  # Do not use locally cached data.
    acline_w_bus: ModelDF = model.network.section_with_bus(section='acline',
                                                           inplace=False)
    print(f'acline_w_bus.columns: {acline_w_bus.columns}')


def append_bus_info_to_network_dfs(raw_path: str | Path = None):
    """
    Example: ...
    """
    print('APPEND BUS INFO EXAMPLE')
    model = Model(file_path_or_json=raw_path,  # Path to the .raw or .rawx file
                  name='my_model',  # Give your model a convenient name.
                  force_recalculate=False)  # Do not use locally cached data.
    # Update Model.network DataFrames with additional columns to provide
    # more information on each bus.
    model.network.append_bus_info_to_dfs()
    print('Examples:')
    print(f'  model.network.acline.columns: \n'
          f'    {model.network.acline.columns}')
    print(f'  model.network.generator.columns: \n'
          f'    {model.network.generator.columns}')


def graph_example(raw_path: str | Path = None):
    """
    Example: Build a one-line diagram using graph theory (networkx library)
    """
    print('[[GRAPH EXAMPLE]]')
    model = Model(file_path_or_json=raw_path,  # Path to the .raw or .rawx file
                  name='my_model',  # Give your model a convenient name.
                  force_recalculate=False)  # Do not use locally cached data.
    # Create a graph object.
    graph = model.network.graph(regenerate=True, empty_ok=False)

    # Find all paths between 2 buses
    import networkx as nx
    node_a = ('bus', 151)
    node_b = ('bus', 153)
    maximum_path_length_to_find = 5
    try:
        paths = nx.all_simple_paths(graph, node_a, node_b, cutoff=maximum_path_length_to_find)
    except nx.exception.NodeNotFound as e:
        warnings.warn(str(e))
        print('A few nodes:')
        for node in list(graph.nodes)[:10]:
            print(f'    Node: {node}')
    print(f'Paths from {node_a} to {node_b}')
    for path in paths:
        print(path)


if __name__ == '__main__':
    # Optionally, clear your cache.
    clear_site_cache()

    DEFAULT_DIRECTORY: Path = Path(__file__).parent / "data"

    raw_path: Path = DEFAULT_DIRECTORY / r"Model_1.raw"
    model: Model = basic_example(raw_path=raw_path)

    model_info_example(raw_path=raw_path)
    filter_model_inplace_example(raw_path=raw_path)
    filtered_model_copy_example(raw_path=raw_path)
    cache_example(raw_path=raw_path)
    csv_export_example(raw_path=raw_path)
    network_section_with_bus_info(raw_path=raw_path)
    graph_example(raw_path=raw_path)
