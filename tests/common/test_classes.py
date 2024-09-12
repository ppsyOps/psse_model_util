import pytest
import pandas as pd
from copy import deepcopy

from psse_model_util.common.classes import ModelDF


def test_modeldf_initialization():
    df = pd.DataFrame({'A': [1, 2, 3], 'B': [4, 5, 6]})
    meta = {'bus_cols': ['A'], 'id_cols': ['B'], 'data_type': ['int', 'int']}
    model_df = ModelDF(df, meta=meta)

    assert isinstance(model_df, ModelDF)
    assert model_df.meta == meta
    assert model_df.bus_cols == ['A']
    assert model_df.id_cols == ['B']
    assert model_df.data_type == ['int', 'int']


def test_modeldf_setters():
    df = pd.DataFrame({'A': [1, 2, 3], 'B': [4, 5, 6]})
    model_df = ModelDF(df)

    model_df.bus_cols = ['A', 'B']
    model_df.id_cols = ['A']
    model_df.data_type = ['int', 'int']

    assert model_df.bus_cols == ['A', 'B']
    assert model_df.id_cols == ['A']
    assert model_df.data_type == ['int', 'int']


def test_modeldf_copy():
    df = pd.DataFrame({'A': [1, 2, 3], 'B': [4, 5, 6]})
    meta = {'bus_cols': ['A'], 'id_cols': ['B'], 'data_type': ['int', 'int']}
    model_df = ModelDF(df, meta=meta)

    model_df_copy = model_df.copy(deep=True)

    # Check that the copy is a new instance
    assert model_df_copy is not model_df

    # Check that the dataframes are equal
    pd.testing.assert_frame_equal(model_df, model_df_copy)

    # Check that meta data is deeply copied
    assert model_df_copy.meta == model_df.meta
    assert model_df_copy.meta is not model_df.meta

    # Modify original meta and check that the copy's meta remains unchanged
    model_df.meta['bus_cols'] = ['B']
    assert model_df_copy.meta['bus_cols'] == ['A']


def test_modeldf_filter_preserves_meta():
    df = pd.DataFrame({'A': [1, 2, 3], 'B': [4, 5, 6]})
    meta = {'bus_cols': ['A'], 'id_cols': ['B'], 'data_type': ['int', 'int']}
    model_df = ModelDF(df, meta=meta)
    model_df = model_df[model_df['A'] > 1]
    assert len(model_df) == 2
    assert model_df.meta == meta


def test_modeldf_merge_preserves_meta():
    df1 = pd.DataFrame({'A': [1, 2, 3], 'B': [4, 5, 6]})
    meta1 = {'bus_cols': ['A'], 'id_cols': ['B'], 'data_type': ['int', 'int']}
    model_df1 = ModelDF(df1, meta=meta1)

    df2 = pd.DataFrame({'A': [1, 2, 3], 'C': [7, 8, 9]})
    meta2 = {'bus_cols': ['A'], 'id_cols': ['C'], 'data_type': ['int', 'str']}
    model_df2 = ModelDF(df2, meta=meta2)

    # Merge the two ModelDFs
    merged_model_df = model_df1.merge(model_df2, on='A')

    # Check that the merged object is a ModelDF and meta is preserved
    assert isinstance(merged_model_df, ModelDF)
    assert merged_model_df.meta == model_df1.meta


def test_modeldf_query_preserves_meta():
    df = pd.DataFrame({'A': [1, 2, 3], 'B': [4, 5, 6]})
    meta = {'bus_cols': ['A'], 'id_cols': ['B'], 'data_type': ['int', 'int']}
    model_df = ModelDF(df, meta=meta)

    # Query the ModelDF
    queried_model_df = model_df.query('A > 1')

    # Check that the queried object is a ModelDF and meta is preserved
    assert isinstance(queried_model_df, ModelDF)
    assert queried_model_df.meta == meta


if __name__ == "__main__":
    pytest.main()
