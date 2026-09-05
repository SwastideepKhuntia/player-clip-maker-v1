"""
Sync Engine — Offset-based time synchronization with halftime awareness.

Handles the gap between match-time (from CSV) and video-time by applying:
  - A base offset (for pre-kickoff preamble in the video)
  - A halftime break duration (for the gap between halves in the video)
"""

import logging

logger = logging.getLogger(__name__)


def apply_offset(
    events: list[dict],
    halves_include: str,
    fh_kickoff: float,
    sh_kickoff: float,
    et1_kickoff: float = 0.0,
    et2_kickoff: float = 0.0,
    video_sources: dict = None,
) -> list[dict]:
    """
    Apply time offset to each event so CSV timestamps align with video time.
    Also handles filtering out halves if requested and tags events with specific source_video if provided.
    """
    synced = []
    first_half_count = 0
    second_half_count = 0
    et_count = 0
    video_sources = video_sources or {}

    for event in events:
        period = event.get("period", "FirstHalf")

        # 1. Filter by Halves Include Setting
        if halves_include == "first" and period != "FirstHalf":
            continue
        if halves_include == "second" and period != "SecondHalf":
            continue
        # "full" and "both" — no filtering, include all periods

        # 2. Assign source video file per period if separate files uploaded
        source_video = None
        if period == "FirstHalf":
            source_video = video_sources.get("first") or video_sources.get("full") or video_sources.get("default")
        elif period == "SecondHalf":
            source_video = video_sources.get("second") or video_sources.get("full") or video_sources.get("default")
        elif period == "ETFirstHalf":
            source_video = video_sources.get("et1") or video_sources.get("full") or video_sources.get("default")
        elif period == "ETSecondHalf":
            source_video = video_sources.get("et2") or video_sources.get("full") or video_sources.get("default")
        else:
            source_video = video_sources.get("full") or video_sources.get("default")

        # 3. Time Synchronization
        has_separate_2h_video = bool(video_sources.get("second"))

        if period == "FirstHalf":
            video_time = event["time_sec"] + fh_kickoff
            first_half_count += 1

        elif period == "SecondHalf":
            # In football CSVs (like WhoScored/Opta), 2H minutes start at 45 (or 45:00 = 2700s)
            raw_sec = event["time_sec"]
            if raw_sec >= 2700:
                elapsed_in_2h = raw_sec - 2700
            else:
                elapsed_in_2h = raw_sec

            if has_separate_2h_video:
                # User uploaded a separate 2nd Half video file:
                # The video starts at 00:00 of 2H video, so offset is from sh_kickoff in that 2H file
                video_time = elapsed_in_2h + sh_kickoff
            else:
                # User uploaded a single full-match 90m video:
                # 2H starts after the 1st half and halftime break (sh_kickoff in the full video)
                video_time = elapsed_in_2h + sh_kickoff
            second_half_count += 1

        elif period == "ETFirstHalf":
            raw_sec = event["time_sec"]
            elapsed_in_et1 = raw_sec - 5400 if raw_sec >= 5400 else raw_sec
            video_time = elapsed_in_et1 + et1_kickoff
            et_count += 1

        elif period == "ETSecondHalf":
            raw_sec = event["time_sec"]
            elapsed_in_et2 = raw_sec - 6300 if raw_sec >= 6300 else raw_sec
            video_time = elapsed_in_et2 + et2_kickoff
            et_count += 1

        else:
            video_time = event["time_sec"] + fh_kickoff

        video_time = max(0.0, video_time)

        item = {
            **event,
            "video_time": round(video_time, 2),
        }
        if source_video:
            item["source_video"] = source_video

        synced.append(item)

    logger.info(f"Applied 1H={fh_kickoff}s, 2H={sh_kickoff}s, ET1={et1_kickoff}s, ET2={et2_kickoff}s "
                f"| Filter mode: {halves_include} "
                f"({first_half_count} 1H, {second_half_count} 2H, {et_count} ET events)")

    return synced
