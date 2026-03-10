from pathlib import Path
from typing import TYPE_CHECKING

from aptdata.core.dataset import IDataset
from aptdata.core.system import BaseComponent, IContext
from aptdata.plugins.dataset import InMemoryDataset
from aptdata.plugins.local_fs import CSVReader
from aptdata.plugins.transform.pandas import PandasTransformComponent

if TYPE_CHECKING:
    import pandas as pd

from domain.transformations import aggregate_player_stats_logic, clean_match_data_logic

# Default path for mock data; can be overridden via constructor
DEFAULT_MOCK_DATA_PATH = Path(__file__).parent.parent / "data" / "raw" / "matches_mock.csv"


class IngestMatchDataComponent(BaseComponent):
    """Bronze component: Reads mock CSV and pushes to memory.
    No strict validation."""

    file_path: str = str(DEFAULT_MOCK_DATA_PATH)

    def validate_inputs(self, inputs: list[IDataset]) -> bool:
        return True

    def execute(self, inputs: list[IDataset]) -> list[IDataset]:
        # Utiliza o leitor nativo do framework (CSVReader)
        # zero I/O de pandas aqui. O CSVReader já gera o Dataset InMemory.
        reader = CSVReader(self.file_path)
        out_ds = reader.read()
        return [out_ds]


class CleanMatchDataComponent(BaseComponent):
    """Silver component: Cleans and standardises types.
    Expects data to comply with SilverMatchModel on output via BaseFlow contract."""

    def validate_inputs(self, inputs: list[IDataset]) -> bool:
        return len(inputs) > 0

    def execute(self, inputs: list[IDataset]) -> list[IDataset]:
        if getattr(self, "context", None):
            self.context.logger.info("Iniciando limpeza da camada Silver com validação Pydantic")

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

        out_ds = InMemoryDataset(uri=f"memory://{self.component_id}_output")
        out_ds.write(cleaned_records)
        return [out_ds]


class AggregateTeamStatsComponent(PandasTransformComponent):
    """Gold component: Aggregates total goals by team."""

    def transform(self, df: "pd.DataFrame", context: IContext) -> "pd.DataFrame":
        context.logger.info("Iniciando agregação da camada Gold")
        return aggregate_player_stats_logic(df)
