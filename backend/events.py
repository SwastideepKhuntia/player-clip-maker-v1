"""
Event Scoring, Filtering, and Time-Buffer Mapping.

Assigns an importance score to each event type, filters low-value events,
and adds clip start/end times with overlap merging.
"""

# Importance scores for event types (case-insensitive keys)
EVENT_SCORES: dict[str, int] = {
    # Goals & Shots
    "goal": 5,
    "assist": 5,
    "key pass": 4,
    "key_pass": 4,
    "shot": 3,
    "shot on target": 4,
    "shot_on_target": 4,
    "shot off target": 3,
    "woodwork (shot on post)": 4,
    "blocked shot": 3,
    "missedshots": 2,
    "missed shots": 2,

    # Passing & Creation
    "through ball": 4,
    "cross": 3,
    "long pass": 2,
    "chipped pass": 2,
    "free kick": 3,
    "corner": 3,
    "throw in": 1,
    "pass": 1,
    "chance created": 4,
    "chance_created": 4,

    # Dribbling & Take-ons
    "successful dribble": 3,
    "unsuccessful dribble": 2,
    "dribble": 3,
    "takeon": 3,
    "take on": 3,
    "take_on": 3,
    "carry": 1,
    "progressive carry": 3,
    "progressive_carry": 3,

    # Defending & Tackles
    "successful tackle": 3,
    "was dribbled": 2,
    "tackle": 3,
    "interception": 3,
    "clearance": 2,
    "block": 2,
    "blocked pass": 2,
    "aerial won": 3,
    "aerial lost": 1,
    "aerial": 2,
    "ball recovery": 2,
    "ballrecovery": 2,
    "loss of possession": 2,
    "dispossessed": 2,
    "error": 2,

    # Goalkeeping
    "save": 4,
    "claim": 3,
    "punch": 3,
    "smother": 3,
    "keeper sweeper": 3,
    "keeper pickup": 2,

    # Substitutions
    "substitution on": 3,
    "substitution off": 3,
    "substitutionon": 3,
    "substitutionoff": 3,
    "substitution": 3,

    # General & Disciplinary
    "foul": 2,
    "foul won": 3,
    "challenge": 2,
    "offside": 1,
    "balltouch": 1,
    "ball touch": 1,
    "ball_touch": 1,
    "touch": 1,
}

DEFAULT_SCORE = 1  # For unknown event types


def score_and_filter(events: list[dict], action_types: str, min_score: int, min_xt: float, top_x: int) -> list[dict]:
    """Assign a priority score to events and filter by selected types, minimum score, and minimum xT.

    `action_types` is a comma-separated string. If "all", no type filtering is applied.
    """
    allow_all = action_types.strip().lower() == "all"
    check_prog = False
    check_def = False

    if not allow_all:
        allowed_types = {a.strip().lower() for a in action_types.split(",") if a.strip()}
        if "progressive actions" in allowed_types:
            check_prog = True
            allowed_types.remove("progressive actions")
        if "defensive actions" in allowed_types:
            check_def = True
            allowed_types.remove("defensive actions")
    else:
        allowed_types = set()

    processed_events = []
    
    for e in events:
        event_type = e.get("event", "").lower().strip()
        extra = e.get("extra_data", {})
        outcome = str(extra.get("outcometype", "")).lower()
        is_successful = outcome == "successful"

        # --- Progressive Identification ---
        is_progressive = False
        if event_type in ["shot", "goal", "assist", "chance_created", "chance created", "key_pass", "key pass", "cross", "takeon", "take on", "take_on", "progressive carry", "progressive pass"]:
            if is_successful or "shot" in event_type or "goal" in event_type or "assist" in event_type:
                is_progressive = True

        try:
            p_pass = float(extra.get("prog_pass", 0))
            if p_pass > 5.0 and is_successful:
                is_progressive = True
        except (ValueError, TypeError): pass

        try:
            p_carry = float(extra.get("prog_carry", 0))
            if p_carry > 5.0 and is_successful:
                is_progressive = True
        except (ValueError, TypeError): pass

        # --- Defensive Identification ---
        is_defensive = False
        if event_type in ["tackle", "interception", "clearance", "blocked shot", "blocked_shot", "blocked pass", "blockedpass", "blocked_pass", "ballrecovery", "ball recovery", "ball_recovery", "challenge", "aerial", "aerial won", "aerial_won"]:
            is_defensive = True

        # --- Filter Logic ---
        if not allow_all:
            raw_type = str(extra.get("type", "")).lower().strip()
            clean_et = event_type.replace(" ", "").replace("_", "")
            type_match = (
                event_type in allowed_types
                or clean_et in allowed_types
                or any(clean_et == at.replace(" ", "").replace("_", "") for at in allowed_types)
                or (raw_type and raw_type in allowed_types)
                or (raw_type and any(raw_type.replace(" ", "").replace("_", "") == at.replace(" ", "").replace("_", "") for at in allowed_types))
            )
            prog_match = check_prog and is_progressive
            def_match = check_def and is_defensive
            if not (type_match or prog_match or def_match):
                continue

        score = EVENT_SCORES.get(event_type, DEFAULT_SCORE)
        
        # Extract xT (Expected Threat)
        xt_val = 0.0
        try:
            val = extra.get("xt")
            if val is not None and str(val).strip() != "":
                xt_val = float(val)
        except (ValueError, TypeError): pass

        processed_events.append({
            **e,
            "score": score,
            "xt": xt_val,
            "is_progressive": is_progressive,
            "is_defensive": is_defensive
        })

    # Apply scoring for the remaining allowed events
    # We can still boost scores based on progressive/defensive logic, or rely entirely on min_xt.
    filtered = [e for e in processed_events if e["score"] >= min_score]

    # 2. Filter based on Min xT
    if min_xt > 0.0:
        filtered = [e for e in filtered if e.get("xt", 0.0) >= min_xt]

    # 3. Filter based on Top X
    if top_x > 0 and len(filtered) > top_x:
        # Select top X highest impact actions by (score, xT)
        filtered.sort(key=lambda x: (x.get("score", 1), x.get("xt", 0.0)), reverse=True)
        filtered = filtered[:top_x]
        
    # Always return events in strict chronological order for natural match replay:
    # 1. FirstHalf (0) -> 2. SecondHalf (1) -> 3. ETFirstHalf (2) -> 4. ETSecondHalf (3)
    period_order = {"FirstHalf": 0, "SecondHalf": 1, "ETFirstHalf": 2, "ETSecondHalf": 3}
    filtered.sort(key=lambda e: (
        period_order.get(e.get("period", "FirstHalf"), 0),
        e.get("minute", 0),
        e.get("second", 0),
        e.get("time_sec", 0.0)
    ))
    return filtered


def add_buffers(
    events: list[dict],
    pre_sec: float = 6.0,
    post_sec: float = 4.0,
    merge_gap: float = 6.0,
    video_duration: float | None = None,
) -> list[dict]:
    """
    Add clip_start and clip_end to each event with overlap merging.

    Overlapping or adjacent clips are merged into a single clip so
    the final video doesn't contain duplicate frames.
    """
    if not events:
        return []

    # Sort strictly by match period first, then by video timestamp within that period
    period_order = {"FirstHalf": 0, "SecondHalf": 1, "ETFirstHalf": 2, "ETSecondHalf": 3}
    sorted_events = sorted(events, key=lambda e: (
        period_order.get(e.get("period", "FirstHalf"), 0),
        e.get("minute", 0),
        e.get("second", 0),
        e.get("video_time", 0.0)
    ))

    # Build raw intervals
    intervals = []
    for event in sorted_events:
        start = max(0.0, event["video_time"] - pre_sec)
        end = event["video_time"] + post_sec
        if video_duration is not None:
            end = min(end, video_duration)
        intervals.append({
            "clip_start": round(start, 2),
            "clip_end": round(end, 2),
            "events": [event],
        })

    # Merge overlapping intervals with explicit merge_gap (only within the same period/source video)
    merged = [intervals[0]]
    for iv in intervals[1:]:
        prev = merged[-1]
        prev_src = prev["events"][0].get("source_video")
        curr_src = iv["events"][0].get("source_video")
        prev_period = prev["events"][0].get("period")
        curr_period = iv["events"][0].get("period")
        
        # If the start of current clip is within the `merge_gap` of the end of the previous clip AND same source video/period:
        if (prev_src == curr_src) and (prev_period == curr_period) and (iv["clip_start"] <= prev["clip_end"] + merge_gap):
            prev["clip_end"] = max(prev["clip_end"], iv["clip_end"])
            prev["events"].extend(iv["events"])
        else:
            merged.append(iv)

    # Flatten back: one dict per merged clip
    result = []
    for i, m in enumerate(merged):
        source_video = m["events"][0].get("source_video") if m["events"] else None
        period = m["events"][0].get("period") if m["events"] else None
        result.append({
            "clip_index": i,
            "clip_start": m["clip_start"],
            "clip_end": m["clip_end"],
            "events": m["events"],
            "event_summary": ", ".join(e.get("event", "Action") for e in m["events"]),
            "source_video": source_video,
            "period": period,
        })

    return result
