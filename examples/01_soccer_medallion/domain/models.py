from pydantic import BaseModel, Field, field_validator


class SilverMatchModel(BaseModel):
    match_id: str = Field(..., description="UUID da partida")
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    date: str

    @field_validator("home_goals", "away_goals", mode="before")
    @classmethod
    def parse_goals(cls, v):
        if v == "null" or v is None or v == "":
            return 0
        return v

class GoldTeamStatsModel(BaseModel):
    team: str
    total_goals_scored: int
    matches_played: int
