import pandas as pd
from pathlib import Path
from typing import Optional

from aptdata.core.decorators import component, pandas_component
from aptdata.core.context import IContext
from aptdata.core.dataset import IDataset
from aptdata.plugins.local_fs import CSVReader

from domain.transformations import clean_match_data_logic, aggregate_player_stats_logic

DEFAULT_MOCK_DATA_PATH = Path(__file__).parent / "data" / "raw" / "matches_mock.csv"

@component("ingest_match_data")
def ingest_match_data(inputs: list[IDataset], context: IContext, file_path: Optional[str] = None) -> list[IDataset]:
    """Bronze Layer: Ingest raw data."""
    context.logger.info("Ingesting raw data from CSV (Bronze)")
    path_to_read = file_path or str(DEFAULT_MOCK_DATA_PATH)
    reader = CSVReader(path_to_read)
    out_ds = reader.read()
    return [out_ds]


@pandas_component("clean_match_data")
def clean_match_data(df: pd.DataFrame, context: IContext) -> pd.DataFrame:
    """Silver Layer: Clean and validate data."""
    context.logger.info("Starting cleaning in Silver layer")
    return clean_match_data_logic(df)


@pandas_component("aggregate_player_stats")
def aggregate_player_stats(df: pd.DataFrame, context: IContext) -> pd.DataFrame:
    """Gold Layer: Aggregates total goals by team."""
    context.logger.info("Starting aggregation in Gold layer")
    return aggregate_player_stats_logic(df)
