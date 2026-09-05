"""
WhoScored Scraper & Event Normalizer — Direct Match Event Extraction
Integrates WhoScored matchCentreData scraping with automatic transformation
into the Player Clip Maker standard event schema.
"""

import json
import re
import logging
from pathlib import Path
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

try:
    from webdriver_manager.chrome import ChromeDriverManager
    HAS_WEBDRIVER_MANAGER = True
except ImportError:
    HAS_WEBDRIVER_MANAGER = False

logger = logging.getLogger(__name__)

def get_headless_driver():
    """Create a stealth headless Chrome driver for WhoScored scraping."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    if HAS_WEBDRIVER_MANAGER:
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            return driver
        except Exception:
            pass

    # Modern Selenium (v4.6+) natively manages drivers automatically without webdriver_manager
    driver = webdriver.Chrome(options=options)
    return driver


def scrape_whoscored_match(url_or_id: str, output_csv_path: str | Path = None) -> tuple[pd.DataFrame, str]:
    """
    Scrape match event data from a WhoScored match URL or Match ID.
    Converts WhoScored events directly into our standard event pipeline format
    (columns: player, team, minute, second, event, period, x, y, endX, endY, etc.)
    and saves to a local CSV in data/csv/.
    """
    url_or_id = str(url_or_id).strip()
    
    if url_or_id.isdigit():
        target_url = f"https://www.whoscored.com/Matches/{url_or_id}/Live"
    elif "whoscored.com" in url_or_id:
        target_url = url_or_id
    else:
        # Check if match ID embedded in text
        match_id_search = re.search(r"(\d{6,8})", url_or_id)
        if match_id_search:
            target_url = f"https://www.whoscored.com/Matches/{match_id_search.group(1)}/Live"
        else:
            raise ValueError("Invalid WhoScored URL or Match ID provided.")

    logger.info(f"Connecting to WhoScored match: {target_url}")
    driver = None
    try:
        driver = get_headless_driver()
        driver.get(target_url)

        # Wait for page to load
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Strategy 1: Attempt direct JavaScript extraction via driver (fastest and most accurate)
        match_json = None
        try:
            match_json = driver.execute_script("return (typeof matchCentreData !== 'undefined') ? matchCentreData : null;")
        except Exception:
            pass

        # Strategy 2: Parse script tag from page_source using robust JSONDecoder.raw_decode
        if not match_json:
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, "html.parser")

            script_tag = soup.find("script", string=re.compile(r"matchCentreData"))
            if not script_tag:
                for s in soup.find_all("script"):
                    if s.string and "matchCentreData" in s.string:
                        script_tag = s
                        break

            if not script_tag or not script_tag.string:
                raise RuntimeError("Could not find matchCentreData script in WhoScored page source.")

            text = script_tag.string
            # Find the position where JSON object starts
            idx = text.find("matchCentreData:")
            if idx == -1:
                idx = text.find("matchCentreData =")
            if idx == -1:
                raise RuntimeError("Could not locate matchCentreData assignment in script.")

            json_start = text.find("{", idx)
            if json_start == -1:
                raise RuntimeError("Could not find start '{' of matchCentreData JSON.")

            json_str = text[json_start:]
            decoder = json.JSONDecoder()
            match_json, _ = decoder.raw_decode(json_str)

        player_id_dict = match_json.get("playerIdNameDictionary", {})
        
        # Also extract players directly from team rosters/lineups in match_json
        for side in ["home", "away"]:
            side_dict = match_json.get(side, {})
            players_list = side_dict.get("players", [])
            for p in players_list:
                p_id = str(p.get("playerId", ""))
                p_name = p.get("name", "")
                if p_id and p_name:
                    player_id_dict[p_id] = p_name

        home_team = match_json.get("home", {}).get("name", "Home Team")
        away_team = match_json.get("away", {}).get("name", "Away Team")
        home_id = match_json.get("home", {}).get("teamId")

        raw_events = match_json.get("events", [])
        if not raw_events:
            raise RuntimeError("No match events found in WhoScored data.")

        # Normalize events to our standard schema
        normalized_rows = []
        for ev in raw_events:
            pid = str(ev.get("playerId")) if ev.get("playerId") is not None else ""
            rel_pid = str(ev.get("relatedPlayerId")) if ev.get("relatedPlayerId") is not None else ""

            player_name = player_id_dict.get(pid) or player_id_dict.get(str(int(float(pid)))) if pid and pid != "None" else ""
            related_player_name = player_id_dict.get(rel_pid) or player_id_dict.get(str(int(float(rel_pid)))) if rel_pid and rel_pid != "None" else ""

            # If substitution event has empty player_name but has related_player_name, assign properly
            if not player_name and related_player_name:
                player_name = related_player_name
            
            team_id = ev.get("teamId")
            team_name = home_team if str(team_id) == str(home_id) else away_team

            type_info = ev.get("type", {})
            event_type = type_info.get("displayName", "Action") if isinstance(type_info, dict) else str(type_info)

            period_info = ev.get("period", {})
            period_name = period_info.get("displayName", "FirstHalf") if isinstance(period_info, dict) else str(period_info)
            
            # Map periods to standard FirstHalf / SecondHalf
            if "1" in period_name or "First" in period_name:
                std_period = "FirstHalf"
            elif "2" in period_name or "Second" in period_name:
                std_period = "SecondHalf"
            elif "Extra1" in period_name or "ET1" in period_name:
                std_period = "ETFirstHalf"
            elif "Extra2" in period_name or "ET2" in period_name:
                std_period = "ETSecondHalf"
            else:
                std_period = "FirstHalf" if ev.get("minute", 0) <= 45 else "SecondHalf"

            # Detailed qualifier and sub-type extraction from WhoScored
            qualifiers = ev.get("qualifiers", [])
            qual_types = [q.get("type", {}).get("displayName", "") for q in qualifiers if isinstance(q, dict)]
            
            is_successful = ev.get("outcomeType", {}).get("displayName") == "Successful"

            # Determine granular event name
            display_event = event_type

            # 1. SHOTS & GOALS
            if "Goal" in qual_types or event_type == "Goal":
                display_event = "Goal"
            elif "ShotOnPost" in qual_types:
                display_event = "Woodwork (Shot on Post)"
            elif "SavedShot" in qual_types or "ShotOnTarget" in qual_types:
                display_event = "Shot on Target"
            elif "BlockedShot" in qual_types or "ShotBlocked" in qual_types:
                display_event = "Blocked Shot"
            elif event_type in ["MissedShots", "MissedShot"]:
                display_event = "Shot off Target"
            elif event_type == "SavedShot":
                display_event = "Shot on Target"

            # 2. PASSES & CHANCES
            elif "IntentionalGoalAssist" in qual_types:
                display_event = "Assist"
            elif "KeyPass" in qual_types:
                display_event = "Key Pass"
            elif "Throughball" in qual_types or "ThroughBall" in qual_types:
                display_event = "Through Ball"
            elif "Cross" in qual_types:
                display_event = "Cross"
            elif "Longball" in qual_types or "LongBall" in qual_types:
                display_event = "Long Pass"
            elif "Chipped" in qual_types:
                display_event = "Chipped Pass"
            elif "Freekick" in qual_types or event_type == "FreeKick":
                display_event = "Free Kick"
            elif "Corner" in qual_types or event_type == "Corner":
                display_event = "Corner"
            elif "ThrowIn" in qual_types or event_type == "ThrowIn":
                display_event = "Throw In"

            # 3. DRIBBLES & TAKE-ONS
            elif event_type in ["TakeOn", "Takeon", "Dribble"]:
                display_event = "Successful Dribble" if is_successful else "Unsuccessful Dribble"

            # 4. TACKLES & DEFENDING
            elif event_type == "Tackle":
                display_event = "Successful Tackle" if is_successful else "Was Dribbled"
            elif event_type == "Interception":
                display_event = "Interception"
            elif event_type == "Clearance":
                display_event = "Clearance"
            elif event_type == "Block" or "BlockedPass" in qual_types:
                display_event = "Block"
            elif event_type in ["Aerial", "AerialDuel", "AerialDuels"]:
                display_event = "Aerial Won" if is_successful else "Aerial Lost"
            elif event_type in ["BallRecovery", "Recovery"]:
                display_event = "Ball Recovery"
            elif event_type == "Dispossessed":
                display_event = "Loss of Possession"
            elif event_type in ["Error", "ErrorLeadingToGoal", "ErrorLeadingToShot"]:
                display_event = "Error"

            # 5. GOALKEEPING
            elif event_type == "Save":
                display_event = "Save"
            elif event_type in ["Claim", "ClaimHigh"]:
                display_event = "Claim"
            elif event_type == "Punch":
                display_event = "Punch"

            # 6. FOULS & OFFSIDES
            elif event_type in ["Foul", "FoulCommitted"]:
                display_event = "Foul"
            elif event_type == "OffsidePass" or event_type == "OffsideGiven":
                display_event = "Offside"

            # 7. SUBSTITUTIONS
            elif event_type == "SubstitutionOn":
                display_event = "Substitution On"
            elif event_type == "SubstitutionOff":
                display_event = "Substitution Off"

            normalized_rows.append({
                "player": player_name,
                "team": team_name,
                "minute": ev.get("minute", 0),
                "second": ev.get("second", 0),
                "event": display_event,
                "raw_event": event_type,
                "period": std_period,
                "x": ev.get("x", 0),
                "y": ev.get("y", 0),
                "endX": ev.get("endX", 0),
                "endY": ev.get("endY", 0),
                "outcome": "Successful" if is_successful else "Unsuccessful"
            })

        df = pd.DataFrame(normalized_rows)

        # Save to CSV if path provided
        clean_home = re.sub(r'\W+', '_', home_team)
        clean_away = re.sub(r'\W+', '_', away_team)
        csv_filename = f"whoscored_{clean_home}_vs_{clean_away}.csv"
        
        if output_csv_path:
            out_file = Path(output_csv_path)
        else:
            base_dir = Path(__file__).resolve().parent.parent
            csv_dir = base_dir / "data" / "csv"
            csv_dir.mkdir(parents=True, exist_ok=True)
            out_file = csv_dir / csv_filename

        df.to_csv(out_file, index=False)
        logger.info(f"Saved {len(df)} scraped WhoScored events to: {out_file}")

        return df, out_file.name

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
