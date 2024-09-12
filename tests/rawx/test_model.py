import pytest
from pathlib import Path

from psse_model_util.model import Model

import pandas as pd
# import numpy as np

data_folder = Path(__file__).parent.parent.parent / r"tests/data"

@pytest.fixture
def sample_model():
    return Model(data_folder / r'sample_v35.rawx')


def test_general_section(sample_model):
    assert hasattr(sample_model.general, 'version')
    assert sample_model.general.version == "35.4"


def test_network_section(sample_model):
    assert hasattr(sample_model.network, 'caseid')
    assert hasattr(sample_model.network, 'rating')


def test_caseid(sample_model):
    caseid_df = sample_model.network.caseid
    assert isinstance(caseid_df, pd.DataFrame)
    assert len(caseid_df) == 1
    assert 'ic' in caseid_df.columns


def test_rating(sample_model):
    rating_df = sample_model.network.rating
    assert isinstance(rating_df, pd.DataFrame)
    assert len(rating_df) > 1
    assert 'irate' in rating_df.columns


def test_solver(sample_model):
    solver_df = sample_model.network.solver
    assert isinstance(solver_df, pd.DataFrame)
    assert len(solver_df) == 1
    assert 'method' in solver_df.columns
    assert 'nondiv' in solver_df.columns
    assert pd.isna(solver_df['nondiv'].iloc[0])  # Check if 'nondiv' column contains NaN


def test_all_network_dataframes(sample_model):
    for attr_name in dir(sample_model.network):
        attr = getattr(sample_model.network, attr_name)
        if not attr_name.startswith('_') and isinstance(attr, pd.DataFrame):
            df = attr
            assert isinstance(df, pd.DataFrame), f"{attr_name} is not a DataFrame"
            assert len(df.columns) == len(set(df.columns)), f"{attr_name} has duplicate column names"
            if attr_name not in ['gne'] and not attr_name.startswith('sub'):
                assert not df.empty, f"{attr_name} DataFrame is empty"