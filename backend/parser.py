"""
CSV Parser — Extracts structured event data from CSV files.
Filters events for a specific player and converts timestamps to seconds.

Supports various CSV formats:
  - Multi-player CSVs with a player column
  - Single-player exports with no player column
"""

import pandas as pd
import unicodedata
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    """Normalize text for accent-insensitive comparison."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def get_players(file_path: str | Path) -> tuple[list[str], list[str], bool, str, dict[str, list[str]]]:
    """Return (player_list, team_list, is_single_player, fallback_name, team_players_map)."""
    df = _read_csv_flexible(file_path)

    player_col = _find_column(df, _PLAYER_CANDIDATES)
    team_col = _find_column(df, _TEAM_CANDIDATES)
    fallback_name = Path(file_path).stem.replace("_", " ").replace("-", " ").title()
    
    players = []
    if player_col is not None:
        players = df[player_col].dropna().unique().tolist()
        players = [str(p).strip() for p in players if str(p).strip()]
        players = sorted(players, key=str.lower)

    teams = []
    if team_col is not None:
        teams = df[team_col].dropna().unique().tolist()
        teams = [str(t).strip() for t in teams if str(t).strip()]
        teams = sorted(teams, key=str.lower)

    team_players = {}
    if team_col is not None and player_col is not None:
        for t in teams:
            t_df = df[df[team_col].astype(str).str.strip().str.lower() == str(t).strip().lower()]
            p_list = t_df[player_col].dropna().unique().tolist()
            team_players[t] = sorted([str(p).strip() for p in p_list if str(p).strip()], key=str.lower)

    is_single = (player_col is None and team_col is None)
    return players, teams, is_single, fallback_name, team_players


def parse_csv(file_path: str | Path, player_name: str = "", team_name: str = "") -> list[dict]:
    """
    Parse a CSV and return events for the given player OR team.
    """
    df = _read_csv_flexible(file_path)
    return parse_df(df, player_name, team_name)

def parse_df(df: pd.DataFrame, player_name: str = "", team_name: str = "") -> list[dict]:
    """
    Core parsing engine extracted to accept a DataFrame directly (for API integrations).
    """

    # --- Identify columns ---
    player_col = _find_column(df, _PLAYER_CANDIDATES)
    minute_col = _find_column(df, _MINUTE_CANDIDATES)
    second_col = _find_column(df, _SECOND_CANDIDATES)
    event_col = _find_column(df, _EVENT_CANDIDATES)
    time_col = _find_column(df, _TIME_CANDIDATES)
    period_col = _find_column(df, _PERIOD_CANDIDATES)

    logger.info(f"Detected columns → player={player_col}, minute={minute_col}, "
                f"second={second_col}, event={event_col}, time={time_col}, period={period_col}")

    missing = []
    if minute_col is None and time_col is None:
        missing.append("Minute/Time")
    if event_col is None:
        missing.append("Event")

    if missing:
        cols = list(df.columns)
        logger.error(f"Missing required columns: {missing}. Available: {cols}")
        
        # Super-friendly Insight90 error detection
        cols_lower = [str(c).lower().strip() for c in cols]
        if "name" in cols_lower and "count" in cols_lower and len(cols) <= 4:
            raise ValueError(
                "You uploaded a SUMMARY CSV (player names and counts) instead of EVENT Data! "
                "The app needs exact match timestamps to cut the video. "
                "Please download the 'Event Log', 'Match Actions', or 'Timeline Data' CSV from Insight90 "
                "that includes 'Minute', 'Event', 'Player', and 'Team' columns."
            )
            
        raise ValueError(
            f"Missing required columns for video cutting: {missing}. "
            f"Your CSV only has: {cols}. "
            "Make sure to download an Event/Timeline CSV that contains exact Minutes and Seconds."
        )

    # --- Filter by player OR team ---
    team_col = _find_column(df, _TEAM_CANDIDATES)
    
    if player_col is not None and player_name:
        target = _normalize(player_name)
        mask = df[player_col].apply(lambda x: _normalize(str(x)) == target)
        player_df = df[mask].copy()
        if player_df.empty:
            logger.warning(f"No events found for player: {player_name}")
            return []
    elif team_col is not None and team_name:
        target = _normalize(team_name)
        mask = df[team_col].apply(lambda x: _normalize(str(x)) == target)
        player_df = df[mask].copy()
        if player_df.empty:
            logger.warning(f"No events found for team: {team_name}")
            return []
    else:
        # Single-player or full match export — use all rows
        logger.info("Using all rows (no specific player/team filter applied)")
        player_df = df.copy()

    # --- Build event list ---
    events = []
    for _, row in player_df.iterrows():
        try:
            if minute_col is not None:
                minute = int(float(row[minute_col]))
                second = 0
                if second_col and pd.notna(row.get(second_col, None)):
                    second = int(float(row[second_col]))
                time_sec = minute * 60 + second
            elif time_col is not None:
                time_sec = _parse_time_value(row[time_col])
                minute = int(time_sec) // 60
                second = int(time_sec) % 60
            else:
                continue

            event_type = str(row[event_col]).strip().lower() if pd.notna(row[event_col]) else "unknown"

            # Detect period (FirstHalf / SecondHalf / ET)
            period = "FirstHalf"
            if period_col and pd.notna(row.get(period_col, None)):
                raw = str(row[period_col]).strip().lower()
                if "et2" in raw or "second extra" in raw or raw in ["4", "4h"]:
                    period = "ETSecondHalf"
                elif "et1" in raw or "first extra" in raw or "extra" in raw or raw in ["3", "3h"]:
                    period = "ETFirstHalf"
                elif "second" in raw or raw in ["2", "2h"]:
                    period = "SecondHalf"
            else:
                # MVP Auto-inference if the CSV lacks a period/half column
                if minute >= 90:
                    period = "SecondHalf" # Extra time isn't explicitly supported by default without a period col
                elif minute >= 45:
                    period = "SecondHalf"

            # Capture extra data for advanced filtering
            extra_data = {}
            for col in df.columns:
                val = row[col]
                if pd.isna(val):
                    val = None
                extra_data[str(col).lower().strip()] = val

            events.append({
                "time_sec": time_sec,
                "event": event_type,
                "minute": minute,
                "second": second,
                "period": period,
                "extra_data": extra_data,
            })
        except (ValueError, TypeError) as e:
            logger.warning(f"Skipping row due to parse error: {e}")
            continue

    period_order = {"FirstHalf": 0, "SecondHalf": 1, "ETFirstHalf": 2, "ETSecondHalf": 3}
    events.sort(key=lambda e: (period_order.get(e["period"], 0), e["minute"], e["second"], e["time_sec"]))
    logger.info(f"Parsed {len(events)} events for '{player_name}' "
                f"(1H: {sum(1 for e in events if e['period']=='FirstHalf')}, "
                f"2H: {sum(1 for e in events if e['period']=='SecondHalf')})")
    return events


# ---------------------------------------------------------------------------
# Column name candidates (case-insensitive matching)
# ---------------------------------------------------------------------------
_PLAYER_CANDIDATES = [
    "player", "player_name", "playername", "player name",
    "name", "athlete", "footballer", "display_name", "displayname",
    "full_name", "fullname", "full name",
]

_TEAM_CANDIDATES = [
    "team", "team_name", "teamname", "team name",
    "club", "club_name", "side", "possession_team",
]

_MINUTE_CANDIDATES = [
    "minute", "min", "match_minute", "matchminute", "match minute",
    "mins", "minutes", "game_minute",
]

_SECOND_CANDIDATES = [
    "second", "sec", "match_second", "matchsecond", "match second",
    "secs", "seconds", "game_second",
]

_EVENT_CANDIDATES = [
    "event", "event_type", "eventtype", "event type",
    "type", "action", "activity", "event_name", "eventname",
    "play_type", "playtype",
]

_TIME_CANDIDATES = [
    "timestamp", "time", "match_time", "matchtime", "match time",
    "game_time", "gametime", "clock", "time_seconds", "timeseconds",
    "time_sec", "timesec",
]

_PERIOD_CANDIDATES = [
    "period", "half", "match_half", "matchhalf", "match_period",
    "game_half", "game_period", "phase",
]


def _read_csv_flexible(file_path: str | Path) -> pd.DataFrame:
    """Read CSV with flexible detection of delimiters and encoding."""
    file_path = Path(file_path)

    for encoding in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
        for sep in [",", ";", "\t", "|"]:
            try:
                df = pd.read_csv(file_path, encoding=encoding, sep=sep)
                if len(df.columns) > 1:
                    df.columns = [c.strip() for c in df.columns]
                    logger.info(f"Read CSV with encoding={encoding}, sep='{sep}', "
                                f"columns={list(df.columns)}, rows={len(df)}")
                    return df
            except Exception:
                continue

    logger.warning("Flexible CSV read failed, falling back to default pd.read_csv")
    df = pd.read_csv(file_path)
    df.columns = [c.strip() for c in df.columns]
    return df


def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Find the first matching column name (case-insensitive, whitespace-tolerant)."""
    col_map = {c.lower().strip(): c for c in df.columns}
    for name in candidates:
        if name.lower() in col_map:
            return col_map[name.lower()]
    return None


def _parse_time_value(value) -> float:
    """Parse various time formats into seconds."""
    if pd.isna(value):
        return 0.0

    s = str(value).strip()

    if ":" in s:
        parts = s.split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])

    return float(s)
