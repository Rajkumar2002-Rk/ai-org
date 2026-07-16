"""Competitor data providers.

Each provider runs live when its API key is configured, and otherwise
returns realistic mock data so competitive intelligence works without
external services. All providers share the same shape:

    competitor = {"name": str, "reviews": [str, ...]}
"""
import logging
import urllib.parse

import httpx

from app.config import settings

logger = logging.getLogger("ba.providers")


def _maps_search_url(name: str, city: str) -> str:
    q = urllib.parse.quote_plus(f"{name} {city}".strip())
    return f"https://www.google.com/maps/search/?api=1&query={q}"


def _maps_place_url(place_id: str) -> str:
    return f"https://www.google.com/maps/place/?q=place_id:{place_id}"

_MOCK_REVIEWS = [
    "Service was painfully slow, waited 40 minutes just to order.",
    "Staff were rude and seemed like they didn't want to be there.",
    "The app/website kept crashing when I tried to book online.",
    "Prices keep going up but the quality keeps going down.",
    "Could never get anyone on the phone to confirm my booking.",
    "Place was dirty and tables weren't cleaned between customers.",
    "Online ordering is a nightmare, payment failed three times.",
    "No way to track my order, had no idea when it would arrive.",
    "They lost my reservation even though I booked weeks ahead.",
    "Loyalty rewards never actually apply at checkout.",
]


def _mock_competitors(business_type: str, city: str) -> list[dict]:
    base = business_type.title() if business_type else "Local Business"
    names = [
        f"{base} on Main",
        f"{city} {base} Co.",
        f"The {base} House",
        f"{base} Express",
        f"Downtown {base}",
    ]
    out = []
    for i, name in enumerate(names):
        # Rotate the mock reviews so each competitor looks distinct.
        reviews = _MOCK_REVIEWS[i:] + _MOCK_REVIEWS[:i]
        out.append(
            {
                "name": name,
                "reviews": reviews[:4],
                "maps_url": _maps_search_url(name, city),
            }
        )
    return out


async def fetch_competitors(
    business_type: str, city: str, state: str
) -> tuple[list[dict], bool, bool]:
    """Return (competitors, used_live, yelp_used). Falls back to mock on any gap."""
    if not (settings.google_places_api_key and business_type and city):
        return _mock_competitors(business_type or "business", city or "your area"), False, False

    try:
        competitors = await _fetch_google_places(business_type, city, state)
    except Exception:  # pragma: no cover - network failures
        logger.exception("Google Places fetch failed; using mock data")
        return _mock_competitors(business_type, city), False, False

    # Google may legitimately return nothing (e.g. the classic Places API
    # isn't enabled) — fall back to mock so the user still sees insights.
    if not competitors:
        logger.warning("Google Places returned no results; using mock data")
        return _mock_competitors(business_type, city), False, False

    # Yelp enrichment is best-effort: a Yelp failure must never discard the
    # real Google data we already have. Track whether Yelp actually helped so
    # we can attribute it honestly.
    yelp_used = False
    if settings.yelp_api_key:
        for c in competitors:
            try:
                extra = await _fetch_yelp_reviews(c["name"], city)
                if extra:
                    c["reviews"].extend(extra)
                    yelp_used = True
            except Exception:  # pragma: no cover
                logger.warning("Yelp enrichment failed for %s", c["name"])

    return competitors, True, yelp_used


async def _fetch_google_places(
    business_type: str, city: str, state: str
) -> list[dict]:
    query = f"{business_type} in {city} {state}".strip()
    async with httpx.AsyncClient(timeout=20) as client:
        search = await client.get(
            "https://maps.googleapis.com/maps/api/place/textsearch/json",
            params={"query": query, "key": settings.google_places_api_key},
        )
        search.raise_for_status()
        results = search.json().get("results", [])[:5]

        competitors: list[dict] = []
        for place in results:
            place_id = place.get("place_id")
            name = place.get("name", "Competitor")
            reviews: list[str] = []
            if place_id:
                detail = await client.get(
                    "https://maps.googleapis.com/maps/api/place/details/json",
                    params={
                        "place_id": place_id,
                        "fields": "name,reviews",
                        "key": settings.google_places_api_key,
                    },
                )
                detail.raise_for_status()
                result = detail.json().get("result", {})
                reviews = [r.get("text", "") for r in result.get("reviews", []) if r.get("text")]
            maps_url = _maps_place_url(place_id) if place_id else _maps_search_url(name, city)
            competitors.append({"name": name, "reviews": reviews, "maps_url": maps_url})
        return competitors


async def _fetch_yelp_reviews(name: str, city: str) -> list[str]:
    headers = {"Authorization": f"Bearer {settings.yelp_api_key}"}
    async with httpx.AsyncClient(timeout=20, headers=headers) as client:
        match = await client.get(
            "https://api.yelp.com/v3/businesses/search",
            params={"term": name, "location": city, "limit": 1},
        )
        match.raise_for_status()
        businesses = match.json().get("businesses", [])
        if not businesses:
            return []
        biz_id = businesses[0]["id"]
        reviews_resp = await client.get(
            f"https://api.yelp.com/v3/businesses/{biz_id}/reviews"
        )
        reviews_resp.raise_for_status()
        return [r.get("text", "") for r in reviews_resp.json().get("reviews", []) if r.get("text")]
