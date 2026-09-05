import os
import requests
import pandas as pd
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)
load_dotenv()

API_KEY = os.getenv("API_FOOTBALL_KEY", "").strip()

def search_fixture(query: str):
    pass

def fetch_events_as_df(fixture_id: str) -> pd.DataFrame:
    """
    Connect to football-data.org, download the Match metadata,
    and convert their Goals, Cards, and Subs into our Pipeline's native Pandas Schema.
    """
    if not API_KEY:
        raise ValueError("Missing API_FOOTBALL_KEY in .env file! Please add your X-Auth-Token.")
        
    url = f"https://api.football-data.org/v4/matches/{fixture_id}"
    headers = {
        "X-Auth-Token": API_KEY
    }
    
    logger.info(f"Downloading Match Data from football-data.org for ID: {fixture_id}...")
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        raise ConnectionError(f"API Error {response.status_code}: {response.text}")
        
    data = response.json()
    
    # football-data.org does not provide granular passes/tackles in their standard tier, 
    # but they do provide Goals, Bookings, and Substitutions.
    rows = []
    
    home_team = data.get("homeTeam", {}).get("name", "Home")
    away_team = data.get("awayTeam", {}).get("name", "Away")
    
    # 1. Parse Goals
    for g in data.get("goals", []):
        scorer = g.get("scorer", {}).get("name")
        minute = g.get("minute", 0)
        if scorer:
            rows.append({
                "player": scorer,
                "minute": minute,
                "second": 0,
                "event": f"Goal {g.get('type', '')}".strip(),
                "team": home_team, # Simplified for MVP
                "period": "FirstHalf" if minute <= 45 else "SecondHalf"
            })
        # If there's an assist, log it too!
        assist = g.get("assist", {}).get("name")
        if assist:
            rows.append({
                "player": assist,
                "minute": minute,
                "second": 0,
                "event": "Assist",
                "team": home_team,
                "period": "FirstHalf" if minute <= 45 else "SecondHalf"
            })
            
    # 2. Parse Bookings (Yellow/Red Cards)
    for b in data.get("bookings", []):
        player = b.get("player", {}).get("name")
        minute = b.get("minute", 0)
        card_type = b.get("card", "Booking")
        if player:
            rows.append({
                "player": player,
                "minute": minute,
                "second": 0,
                "event": f"Foul {card_type}",
                "team": away_team,
                "period": "FirstHalf" if minute <= 45 else "SecondHalf"
            })
            
    # 3. Parse Substitutions
    for s in data.get("substitutions", []):
        player_in = s.get("playerIn", {}).get("name")
        player_out = s.get("playerOut", {}).get("name")
        minute = s.get("minute", 0)
        
        if player_in:
            rows.append({"player": player_in, "minute": minute, "second": 0, "event": "Substitution In", "team": "Unknown", "period": "FirstHalf" if minute <= 45 else "SecondHalf"})
        if player_out:
            rows.append({"player": player_out, "minute": minute, "second": 0, "event": "Substitution Out", "team": "Unknown", "period": "FirstHalf" if minute <= 45 else "SecondHalf"})

    if not rows:
        raise ValueError(f"No Goals, Cards, or Subs found for Match ID {fixture_id}. Note: football-data.org does not natively track Pass/Carry/Tackle.")
        
    df = pd.DataFrame(rows)
    logger.info(f"Successfully converted {len(df)} API events into Pandas DataFrame.")
    return df
