from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

from domain.models import SilverMatchModel


def clean_match_data_logic(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pure python logic for Silver Layer: Clean and validate data natively."""
    cleaned = []
    seen_ids = set()

    for row in records:
        match_id = row.get('match_id')

        # Drop nulls on crucial fields
        if not match_id or match_id == "null":
            continue

        # Drop duplicates
        if match_id in seen_ids:
            continue

        seen_ids.add(match_id)

        # Validate and coerce using Pydantic (this casts 'null' to 0)
        try:
            validated = SilverMatchModel.model_validate(row)
            cleaned.append(validated.model_dump())
        except Exception:
            # If a record completely fails validation, we skip it
            continue

    return cleaned


def aggregate_player_stats_logic(df: "pd.DataFrame") -> "pd.DataFrame":
    """Pure pandas logic for Gold Layer: Aggregates total goals by team."""
    import pandas as pd

    home_stats = df.groupby('home_team').agg(
        total_goals_scored=('home_goals', 'sum'),
        matches_played=('match_id', 'count')
    ).reset_index().rename(columns={'home_team': 'team'})

    away_stats = df.groupby('away_team').agg(
        total_goals_scored=('away_goals', 'sum'),
        matches_played=('match_id', 'count')
    ).reset_index().rename(columns={'away_team': 'team'})

    combined = pd.concat([home_stats, away_stats], ignore_index=True)
    gold_stats = combined.groupby('team').sum().reset_index()
    return gold_stats
