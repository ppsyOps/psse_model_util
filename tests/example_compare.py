"""
Test script for compare.py

This script contains unit tests for the ModelComparison class and its methods
in the compare.py module. It uses pytest for testing and includes boundary/edge
cases for argument testing.

Usage:
    pytest test_compare.py

Note: This script assumes the project structure as described in psse_model_util_dir.txt.
"""

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))

from psse_model_util.compare import ModelComparison, Model
from psse_model_util.common.constants import INCLUDE_AREAS


def compare_example(raw1_path=None,
                    raw2_path=None,
                    force_recalculation: bool = True,
                    export_format='csv',  # 'csv' or 'None'
                    add_bus_info_to_branches=True,
                    include_areas=INCLUDE_AREAS):
    # -------------------------------------------------------------------------
    # Model Comparison Script Execution
    # -------------------------------------------------------------------------
    # Print the raw/rawx file paths.
    print(raw1_path)
    print(raw2_path)

    # Path to the model comparison cache file (.modcomp).
    model_comparison_file = Path(
        f'/cache/{raw1_path.stem}_{raw1_path.stem}.modcomp')
    if not force_recalculation and model_comparison_file.exists():
        # Get the cached model comparison object from disk.
        comparison = ModelComparison(model_comp_file=model_comparison_file)
    else:
        # Load the
        # Load & filter your RAW or RAWX models from disk to Model objects.
        print('Loading model1...')
        model1 = Model(raw1_path)

        # Filter the models to a subset of areas (PJM + 1st tier)
        print('Filtering model1...')
        native_model1 = model1.filter_by_area(areas=include_areas)
        print('Loading model2...')
        model2 = Model(raw2_path)
        print('Filtering model2...')
        native_model2 = model2.filter_by_area(areas=include_areas)

        # Optionally, add bus data directly to branch dataframe
        # (model.network.acline).  This is not necessary but can be helpful to
        # the end user, since this info will be in the exported
        # network_acline.csv file.
        if add_bus_info_to_branches:
            print('Model1: adding bus info to edges/branches...')
            native_model1.network.append_bus_info_to_dfs()
            print('Model2: adding bus info to edges/branches...')
            native_model2.network.append_bus_info_to_dfs()

        # Load the models into a ModelComparison instance
        print('Comparing models...')
        comparison = ModelComparison(native_model1, native_model2)

    if force_recalculation or not comparison.network_df_comparison or not comparison.graph_comparison:
        # Run the comparison of the Model.network pandas dataframes.
        print('Comparing network dataframes...')
        comparison.compare_network_dfs()

        # Filter in place to only records we care about for INCH or
        # IDEV file creation.
        comparison.query_network_df_comparison(inplace=True)

        # Run the comparison of the Model.network.graph edges and
        # nodes (built from the dataframes)
        print('Comparing graphs...')
        comparison.compare_graph()

        # Cache the updated ModelComparison object to a pickle file (.modcomp)
        print(f'Saving model comparison to {comparison.pickle_path}...')
        comparison.to_pickle()

    if export_format == 'csv':
        # Export comparison results to CSV
        print(f'Export to CSV ...')
        comparison.to_csv(models_to_csv=False,
                          df_comparison_to_csv=True,
                          graph_comparison_to_csv=True)
        print('CSV folder:', comparison.csv_folder)

    print('ModelComparison cache file:', comparison.pickle_path)

    print('Test completed successfully.')


if __name__ == '__main__':
    DEFAULT_DIRECTORY: Path = Path(__file__).parent / "data"

    raw1_path: Path = DEFAULT_DIRECTORY / r"sample_34.raw"
    raw2_path: Path = DEFAULT_DIRECTORY / r"sample2_34.raw"
    # raw1_path: Path = DEFAULT_DIRECTORY / r"idc_23S_sum23idctr6p2.rawx"
    # raw2_path: Path = DEFAULT_DIRECTORY / r"data/idc_24s_sum24idctr1p8.raw"

    compare_example(raw1_path=raw1_path,
                    raw2_path=raw2_path,
                    force_recalculation=True,
                    export_format='csv',
                    add_bus_info_to_branches=True,
                    include_areas=INCLUDE_AREAS)
