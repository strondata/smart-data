import pandas as pd

def clean_match_data_logic(df: pd.DataFrame) -> pd.DataFrame:
    """Pure pandas logic for Silver Layer: Clean and validate data."""
    # Drop duplicates, nulls on crucial fields, fillna etc.
    df_cleaned = df.dropna(subset=['match_id']).copy()

    # Handle string 'null' explicitly in the mock data, then fillna and cast
    if 'home_goals' in df_cleaned.columns:
        df_cleaned['home_goals'] = pd.to_numeric(df_cleaned['home_goals'], errors='coerce').fillna(0).astype(int)
    if 'away_goals' in df_cleaned.columns:
        df_cleaned['away_goals'] = pd.to_numeric(df_cleaned['away_goals'], errors='coerce').fillna(0).astype(int)

    columns = [col for col in ['match_id', 'home_team', 'away_team', 'home_goals', 'away_goals', 'date'] if col in df_cleaned.columns]
    return df_cleaned[columns]


def aggregate_player_stats_logic(df: pd.DataFrame) -> pd.DataFrame:
    """Pure pandas logic for Gold Layer: Aggregates total goals by team."""
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
