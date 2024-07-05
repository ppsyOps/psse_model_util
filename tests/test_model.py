from psse_model_util.common.dirs import project_dir
from psse_model_util.model import Model

import pandas as pd

sample_data_file = project_dir / "tests/data/sample.raw"


def test_model():
    model1: Model = Model(sample_data_file)
    # print(model1.transformer.head())

    # List all attributes of the model
    attributes = dir(model1)
    # Filter out special methods and attributes
    properties = [attr for attr in attributes if not attr.startswith('__')]

    expected_dfs = ('header', 'bus_df', 'load_df', 'fixed_shunt_df',
                    'branch_df', 'system_switching_device_df', 'transformer_df',
                    'area_df', 'two_terminal_dc_df', 'vsc_dc_line_df',
                    'impedance_correction_df', 'multi_terminal_dc_df',
                    'inter_area_transfer_df', 'owner_df', 'facts_device_df',
                    'switched_shunt_df', 'induction_machine_df')

    for expected_df in expected_dfs:
        assert expected_df in properties
        # if expected_df == 'header':
        #     assert isinstance(getattr(model1, expected_df), dict)
        #     assert len(getattr(model1, expected_df)) > 0
        # else:
        assert isinstance(getattr(model1, expected_df), pd.DataFrame)
        assert len(getattr(model1, expected_df)) > 0
