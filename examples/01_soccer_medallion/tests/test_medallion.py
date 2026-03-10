import os
import sys

import pytest

from aptdata.core.dataset import DataContractError
from aptdata.plugins.dataset import InMemoryDataset

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from components.soccer_components import CleanMatchDataComponent
from flows.soccer_flows import SilverFlow
from system_oo import SoccerMedallionSystem


def test_system_dependency_injection():
    """Testa se o sistema sobe corretamente com as dependencias e os fluxos"""
    system = SoccerMedallionSystem(system_id="test_system")
    system.setup()

    assert len(system._flows) == 3
    assert system._flows[0].flow_id == "soccer_bronze_flow"
    assert system._flows[1].flow_id == "soccer_silver_flow"
    assert system._flows[2].flow_id == "soccer_gold_flow"

def test_pydantic_validation_fail_fast(monkeypatch):
    """Força um schema errado na camada Silver (output_contract) para testar a validação."""
    flow = SilverFlow(flow_id="test_silver")
    flow.compile() # Instancia o componente

    # Cria um payload "sujo" e "incorreto", que simula uma saida de um componente
    # ou um dataframe que não segue o contrato
    invalid_data = [
        # Missing home_goals and away_goals which are required ints in SilverMatchModel
        {"match_id": "123", "home_team": "Team A", "away_team": "Team B", "date": "2023-10-01"}
    ]
    ds = InMemoryDataset(uri="memory://test")
    ds.write(invalid_data)

    # Let's mock `execute` to return an invalid dataset intentionally
    def bad_execute(self_obj, inputs):
        bad_ds = InMemoryDataset(uri="memory://bad")
        bad_ds.write([{"match_id": "123", "home_team": "Team A"}]) # Missing away_team, goals, date
        return [bad_ds]

    # Monkeypatch the specific class's execute method
    monkeypatch.setattr(CleanMatchDataComponent, "execute", bad_execute)

    with pytest.raises(DataContractError):
        flow.run([ds])

def test_full_pipeline_with_mocked_io(monkeypatch):
    """Mock the ingest component to test the full pipeline in milliseconds."""

    from components.soccer_components import IngestMatchDataComponent

    def mocked_execute(self, inputs):
        # Even though we refactored clean logic to drop null match_ids, it handles normal cases too
        df = [
            {"match_id": "1", "home_team": "A", "away_team": "B", "home_goals": 2, "away_goals": 1, "date": "2023-01-01"},
            {"match_id": "2", "home_team": "C", "away_team": "A", "home_goals": 0, "away_goals": 3, "date": "2023-01-02"},
        ]
        ds = InMemoryDataset(uri="memory://test")
        ds.write(df)
        return [ds]

    monkeypatch.setattr(IngestMatchDataComponent, "execute", mocked_execute)

    system = SoccerMedallionSystem(system_id="mocked_pipeline")
    system.run() # Should succeed without errors and very fast
