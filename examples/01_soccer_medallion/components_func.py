from pathlib import Path

import pandas as pd
from domain.transformations import aggregate_player_stats_logic, clean_match_data_logic

from aptdata.core.context import IContext
from aptdata.core.dataset import IDataset
from aptdata.core.decorators import component, pandas_component
from aptdata.plugins.dataset import InMemoryDataset
from aptdata.plugins.local_fs import CSVReader

DEFAULT_MOCK_DATA_PATH = Path(__file__).parent / "data" / "raw" / "matches_mock.csv"

@component("ingest_match_data")
def ingest_match_data(inputs: list[IDataset], context: IContext, file_path: str | None = None) -> list[IDataset]:
    """Bronze Layer: Ingest raw data."""
    context.logger.info("Ingesting raw data from CSV (Bronze)")
    path_to_read = file_path or str(DEFAULT_MOCK_DATA_PATH)
    reader = CSVReader(path_to_read)
    out_ds = reader.read()
    return [out_ds]


@component("clean_match_data")
def clean_match_data(inputs: list[IDataset], context: IContext) -> list[IDataset]:
    """Silver Layer: Clean and validate data."""
    context.logger.info("Starting cleaning in Silver layer using Pydantic")

    all_records = []
    for ds in inputs:
        data = ds.read()
        if isinstance(data, list):
            all_records.extend(data)
        elif type(data).__name__ == "DataFrame":
            all_records.extend(data.to_dict(orient="records"))
        elif data is not None:
            all_records.append(data)

    cleaned_records = clean_match_data_logic(all_records)

    # Needs to match the original signature return type
    out_ds = InMemoryDataset(uri="memory://clean_match_data_out")
    out_ds.write(cleaned_records)
    return [out_ds]


@pandas_component("aggregate_player_stats")
def aggregate_player_stats(df: pd.DataFrame, context: IContext) -> pd.DataFrame:
    """Gold Layer: Aggregates total goals by team."""
    context.logger.info("Starting aggregation in Gold layer")
    return aggregate_player_stats_logic(df)
