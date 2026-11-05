"""Music & Story Search API Routes.

Primary:  YouTube Data API v3
Fallback: HTML scrape (auto if API fails / quota exceeded)

Quality algorithm:
  1. Fetch 10 candidates from Search API
  2. Batch-fetch duration + viewCount via videos.list
  3. Filter out clips shorter than min_duration (songs ≥ 3 min, stories ≥ 5 min)
  4. Sort survivors by viewCount (most watched = best match)
  5. Return top N results
"""

from fastapi import APIRouter, Query
import urllib.request
import urllib.parse
import urllib.error
import re
import os
import json
import webbrowser

from services.voice_bot_engine import get_content_recommendation, get_story_queries, STORY_CATEGORIES

router = APIRouter(tags=["Music Search"])

# ─────────────────────────────────────────────
# Duration helpers
# ─────────────────────────────────────────────
def _parse_iso_duration(d: str) -> int:
    """Convert ISO 8601 duration (PT3M45S) to total seconds."""
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', d or "")
    if not m:
        return 0
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)


def _enrich_with_details(video_ids: list, api_key: str) -> dict:
    """
    Batch-fetch duration + viewCount for a list of video IDs.
    Returns {video_id: {duration_sec, views}}.
    """
    if not video_ids or not api_key:
        return {}
    try:
        params = urllib.parse.urlencode({
            "part": "contentDetails,statistics",
            "id": ",".join(video_ids),
            "key": api_key
        })
        req = urllib.request.Request(
            "https://www.googleapis.com/youtube/v3/videos?" + params,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        raw = urllib.request.urlopen(req, timeout=10).read().decode()
        data = json.loads(raw)
        result = {}
        for item in data.get("items", []):
            vid_id = item["id"]
            dur = _parse_iso_duration(item.get("contentDetails", {}).get("duration", "PT0S"))
            views = int(item.get("statistics", {}).get("viewCount", 0))
            result[vid_id] = {"duration_sec": dur, "views": views}
        return result
    except Exception as e:
        print(f"[YouTube] videos.list error: {e}")
        return {}


# ─────────────────────────────────────────────
# YouTube Data API v3 — primary
# ─────────────────────────────────────────────
def _youtube_api_search(query: str, max_results: int = 3, min_duration: int = 60) -> list[dict]:
    """
    Full quality-ranked search:
      - Fetches 10 candidates from Search API
      - Enriches with real duration + view count
      - Drops anything shorter than min_duration seconds
      - Sorts survivors by view count (descending)
      - Returns top max_results

    min_duration defaults:
      songs        → 180 s (3 min)
      stories      → 300 s (5 min)
      motivational → 180 s (3 min)
    """
    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key:
        return []

    try:
        params = urllib.parse.urlencode({
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": 10,
            "key": api_key,
            "relevanceLanguage": "hi",
            "regionCode": "IN",
            "order": "relevance",
            "videoEmbeddable": "true"
        })
        req = urllib.request.Request(
            "https://www.googleapis.com/youtube/v3/search?" + params,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        raw = urllib.request.urlopen(req, timeout=10).read().decode()
        data = json.loads(raw)

        SHORTS_KW = {'#shorts', '#short', '#reels', '#reel', 'shorts', 'reels'}

        candidates = []
        for item in data.get("items", []):
            video_id = item.get("id", {}).get("videoId")
            if not video_id:
                continue
            title = item.get("snippet", {}).get("title", query.title())
            if any(kw in title.lower() for kw in SHORTS_KW):
                continue
            candidates.append({
                "name":       title,
                "artist":     item.get("snippet", {}).get("channelTitle", "YouTube"),
                "youtube_id": video_id,
                "url":        f"https://www.youtube.com/embed/{video_id}?autoplay=1"
            })

        if not candidates:
            return []

        # Enrich with duration + views
        details = _enrich_with_details([c["youtube_id"] for c in candidates], api_key)

        # Attach details to each candidate
        for c in candidates:
            d = details.get(c["youtube_id"], {})
            c["duration_sec"] = d.get("duration_sec", 0)
            c["views"]        = d.get("views", 0)

        # Filter: drop clips shorter than min_duration
        before = len(candidates)
        candidates = [c for c in candidates if c["duration_sec"] >= min_duration]
        print(f"[YouTube API] {before} candidates → {len(candidates)} after ≥{min_duration}s filter for: {query!r}")

        if not candidates:
            print(f"[YouTube API] All results too short for {query!r}, relaxing filter to 60s")
            # Relax filter once rather than returning nothing
            candidates = [c for c in [
                {**c2, "duration_sec": details.get(c2["youtube_id"], {}).get("duration_sec", 0),
                        "views":        details.get(c2["youtube_id"], {}).get("views", 0)}
                for c2 in [{
                    "name": item.get("snippet", {}).get("title", query.title()),
                    "artist": item.get("snippet", {}).get("channelTitle", "YouTube"),
                    "youtube_id": item.get("id", {}).get("videoId"),
                    "url": f"https://www.youtube.com/embed/{item.get('id', {}).get('videoId')}?autoplay=1"
                } for item in data.get("items", []) if item.get("id", {}).get("videoId")]
            ] if c["duration_sec"] >= 60]

        # Sort by view count — most watched = best quality match
        candidates.sort(key=lambda c: c["views"], reverse=True)

        top = candidates[:max_results]
        for c in top:
            mins = c["duration_sec"] // 60
            secs = c["duration_sec"] % 60
            print(f"  → {c['name'][:50]} | {mins}m{secs:02d}s | {c['views']:,} views")

        return top

    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == 403 and ("quotaExceeded" in body or "keyInvalid" in body):
            print(f"[YouTube API] Quota/key error — falling back to scrape")
        else:
            print(f"[YouTube API] HTTP {e.code}: {body[:200]}")
        return []
    except Exception as e:
        print(f"[YouTube API] Error for {query!r}: {e}")
        return []


# ─────────────────────────────────────────────
# HTML scrape fallback
# ─────────────────────────────────────────────
def _youtube_scrape_many(query: str, suffix: str = "", max_results: int = 3) -> list[dict]:
    """Fallback: scrape YouTube results page. Returns multiple candidates."""
    try:
        q = urllib.parse.urlencode({"search_query": f"{query} {suffix}".strip()})
        req = urllib.request.Request(
            "https://www.youtube.com/results?" + q,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        html = urllib.request.urlopen(req, timeout=10).read().decode()

        # Exclude IDs that appear as Shorts (/shorts/<id>)
        shorts_ids = set(re.findall(r'/shorts/([a-zA-Z0-9_-]{11})', html))

        # Find all watch?v= IDs (regular videos only)
        all_ids = list(dict.fromkeys(re.findall(r'watch\?v=([a-zA-Z0-9_-]{11})', html)))
        ids = [vid for vid in all_ids if vid not in shorts_ids]

        if ids:
            print(f"[YouTube Scrape] {len(all_ids)} raw → {len(ids)} after shorts filter for: {query!r}")

            # Try to enrich with real duration via API (filters sub-30s clips)
            api_key = os.environ.get("YOUTUBE_API_KEY", "")
            details = _enrich_with_details(ids[:max_results * 3], api_key) if api_key else {}

            results = []
            for vid_id in ids:
                if len(results) >= max_results:
                    break
                dur = details.get(vid_id, {}).get("duration_sec", 0)
                if dur > 0 and dur < 30:
                    continue
                results.append({
                    "name": query.title() if len(results) == 0 else f"{query.title()} (Option {len(results)+1})",
                    "artist": "YouTube",
                    "youtube_id": vid_id,
                    "url": f"https://www.youtube.com/embed/{vid_id}?autoplay=1",
                    "duration_sec": dur, "views": details.get(vid_id, {}).get("views", 0)
                })
            return results
    except Exception as e:
        print(f"[YouTube Scrape] Error for {query!r}: {e}")
    return []


# ─────────────────────────────────────────────
# Unified search: API → scrape fallback
# ─────────────────────────────────────────────
def _youtube_search(query: str, min_duration: int = 60) -> dict | None:
    """Single best result. API first, scrape fallback."""
    results = _youtube_api_search(query, max_results=1, min_duration=min_duration)
    if results:
        return results[0]
    scrape_results = _youtube_scrape_many(query, max_results=1)
    return scrape_results[0] if scrape_results else None


def _youtube_search_many(query: str, max_results: int = 3, min_duration: int = 60) -> list[dict]:
    """Up to max_results quality results. API first, scrape fallback."""
    results = _youtube_api_search(query, max_results=max_results, min_duration=min_duration)
    if results:
        return results
    return _youtube_scrape_many(query, max_results=max_results)


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────
@router.get("/music/youtube")
def search_youtube_track(
    q: str = Query(..., min_length=1),
    min_duration: int = Query(60, description="Minimum video duration in seconds (default 60 = 1 min)")
):
    """Search YouTube — filters short clips, returns top 3 ranked by view count."""
    results = _youtube_search_many(q, max_results=3, min_duration=min_duration)
    source = "youtube_api" if results and results[0].get("views", 0) > 0 else "youtube_scrape"
    if results:
        return {"tracks": results, "source": source}
    return {"tracks": [], "source": source, "error": "No results found"}


@router.get("/music/mood")
def search_by_mood(mood: str = Query(...)):
    """Mood-based music — 3-min minimum, sorted by views."""
    rec = get_content_recommendation(mood)
    tracks = []
    for query in rec.get("queries", []):
        result = _youtube_search(query, min_duration=60)
        if result:
            result["name"] = query.title()
            tracks.append(result)
    return {
        "tracks": tracks, "mood": mood,
        "content_type": rec.get("type", "music"),
        "message": rec.get("message", ""),
        "source": "youtube"
    }


@router.get("/story/youtube")
def search_story(category: str = Query("moral")):
    """Story search — 5-min minimum so we get full episodes, not clips."""
    queries = get_story_queries(category)
    tracks = []
    for query in queries:
        result = _youtube_search(query, min_duration=60)   # 1 minute minimum for stories
        if result:
            result["name"] = query.title()
            result["category"] = category
            tracks.append(result)
    return {
        "tracks": tracks, "category": category,
        "available_categories": list(STORY_CATEGORIES.keys()),
        "source": "youtube"
    }


@router.get("/story/categories")
def list_story_categories():
    return {"categories": list(STORY_CATEGORIES.keys())}


@router.get("/music/open-external")
def open_external_youtube(youtube_id: str = Query(...)):
    """Opens a video in a minimized window that doesn't steal focus (Windows only)."""
    try:
        url = f"https://www.youtube.com/watch?v={youtube_id}&autoplay=1"
        print(f"[Music] Opening external video (minimized): {url}")
        
        if os.name == 'nt': # Windows
            # Style 7 = Minimized, the active window remains active.
            # This allows the Voice Bot to stay in focus while the music plays.
            ps_cmd = f"$wshell = New-Object -ComObject WScript.Shell; $wshell.Run('{url}', 7)"
            import subprocess
            subprocess.Popen(["powershell", "-Command", ps_cmd], shell=True)
        else:
            # Fallback for other OS
            import webbrowser
            webbrowser.open(url)
            
        return {"status": "success", "message": "Browser opened minimized", "url": url}
    except Exception as e:
        print(f"[Music] Error opening browser: {e}")
        return {"status": "error", "message": str(e)}

@router.get("/music/close-external")
def close_external_youtube():
    """Closes any external browser window playing YouTube."""
    try:
        print("[Music] Closing external video...")
        if os.name == 'nt':
            # This aggressively targets processes with 'YouTube' in the window title.
            # Edge and Chrome usually spawn processes per tab/window.
            import os
            os.system('taskkill /F /FI "WINDOWTITLE eq *YouTube*" /T >nul 2>&1')
            # Additionally, kill anything with "YouTube" in the title without wildcards just in case
            os.system('taskkill /F /FI "WINDOWTITLE eq YouTube*" /T >nul 2>&1')
        return {"status": "success", "message": "Closed external windows"}
    except Exception as e:
        print(f"[Music] Error closing browser: {e}")
        return {"status": "error", "message": str(e)}

@router.get("/spotify/search")
def search_tracks(q: str = Query(...)):
    return search_youtube_track(q)
