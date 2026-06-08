"""
BreatheSafe — AQI Data Router (Phase 3)

Endpoints:
  GET /aqi/cities              — list all 29 supported cities
  GET /aqi/latest              — most-recent AQI reading per city
  GET /aqi/rankings            — cities ranked by current india_aqi (worst→best)
  GET /aqi/stats               — overall dataset statistics
  GET /aqi/{city_name}/current — latest reading for one city
  GET /aqi/{city_name}/history — hourly history (default 7 days, max 90)
"""

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, desc, asc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.aqi_data import AQIData
from app.models.monitoring_station import MonitoringStation
from app.models.city import City

router = APIRouter()


# ── Helper: joined row → dict ──────────────────────────────────────────────────
def _row_to_current(city_row, aqi_row) -> dict:
    """Merge City ORM + AQIData ORM objects into a flat response dict."""
    return {
        "city":               city_row.name,
        "state":              city_row.state,
        "latitude":           city_row.latitude,
        "longitude":          city_row.longitude,
        "datetime":           aqi_row.datetime,
        "india_aqi":          aqi_row.india_aqi,
        "india_aqi_category": aqi_row.india_aqi_category,
        "us_aqi":             aqi_row.us_aqi,
        "pm2_5_ugm3":         aqi_row.pm2_5_ugm3,
        "pm10_ugm3":          aqi_row.pm10_ugm3,
        "no2_ugm3":           aqi_row.no2_ugm3,
        "so2_ugm3":           aqi_row.so2_ugm3,
        "co_ugm3":            aqi_row.co_ugm3,
        "o3_ugm3":            aqi_row.o3_ugm3,
        "temperature_c":      aqi_row.temperature_c,
        "wind_speed_kmh":     aqi_row.wind_speed_kmh,
        "humidity_percent":   aqi_row.humidity_percent,
        "season":             aqi_row.season,
        "time_of_day":        aqi_row.time_of_day,
    }


# ── 1. List all cities ────────────────────────────────────────────────────────
@router.get("/cities", response_model=List[dict])
def list_cities(db: Session = Depends(get_db)):
    """Return all 29 supported Indian cities with coordinates."""
    cities = (
        db.query(City)
        .filter(City.is_active == True)
        .order_by(City.name)
        .all()
    )
    return [
        {
            "id":        c.id,
            "name":      c.name,
            "state":     c.state,
            "latitude":  c.latitude,
            "longitude": c.longitude,
        }
        for c in cities
    ]


# ── 2. Latest AQI per city ────────────────────────────────────────────────────
@router.get("/latest", response_model=List[dict])
def latest_all_cities(db: Session = Depends(get_db)):
    """
    Returns the most-recent AQI record for every city.
    Uses a correlated subquery to avoid pulling all 842K rows.
    """
    # Subquery: max datetime per station
    latest_sub = (
        db.query(
            AQIData.station_id,
            func.max(AQIData.datetime).label("max_dt"),
        )
        .group_by(AQIData.station_id)
        .subquery()
    )

    rows = (
        db.query(AQIData, City)
        .join(MonitoringStation, AQIData.station_id == MonitoringStation.id)
        .join(City, MonitoringStation.city_id == City.id)
        .join(
            latest_sub,
            (AQIData.station_id == latest_sub.c.station_id)
            & (AQIData.datetime == latest_sub.c.max_dt),
        )
        .order_by(City.name)
        .all()
    )

    return [_row_to_current(city, aqi) for aqi, city in rows]


# ── 3. Rankings (worst → best AQI) ───────────────────────────────────────────
@router.get("/rankings", response_model=List[dict])
def aqi_rankings(
    order: str = Query("desc", regex="^(asc|desc)$"),
    db: Session = Depends(get_db),
):
    """
    Returns all cities sorted by current india_aqi.
    order=desc  → worst first (default)
    order=asc   → best first
    """
    latest_sub = (
        db.query(
            AQIData.station_id,
            func.max(AQIData.datetime).label("max_dt"),
        )
        .group_by(AQIData.station_id)
        .subquery()
    )

    sort_col = desc(AQIData.india_aqi) if order == "desc" else asc(AQIData.india_aqi)

    rows = (
        db.query(AQIData, City)
        .join(MonitoringStation, AQIData.station_id == MonitoringStation.id)
        .join(City, MonitoringStation.city_id == City.id)
        .join(
            latest_sub,
            (AQIData.station_id == latest_sub.c.station_id)
            & (AQIData.datetime == latest_sub.c.max_dt),
        )
        .order_by(sort_col)
        .all()
    )

    result = []
    for rank, (aqi, city) in enumerate(rows, start=1):
        d = _row_to_current(city, aqi)
        d["rank"] = rank
        result.append(d)
    return result


# ── 4. Dataset statistics ─────────────────────────────────────────────────────
@router.get("/stats", response_model=dict)
def dataset_stats(db: Session = Depends(get_db)):
    """High-level statistics about the seeded dataset."""
    total_rows  = db.query(func.count(AQIData.id)).scalar()
    city_count  = db.query(func.count(City.id)).scalar()
    earliest_dt = db.query(func.min(AQIData.datetime)).scalar()
    latest_dt   = db.query(func.max(AQIData.datetime)).scalar()
    avg_aqi     = db.query(func.avg(AQIData.india_aqi)).scalar()

    # AQI category distribution
    cat_counts = (
        db.query(AQIData.india_aqi_category, func.count(AQIData.id))
        .filter(AQIData.india_aqi_category != None)
        .group_by(AQIData.india_aqi_category)
        .all()
    )

    return {
        "total_records":    total_rows,
        "cities":           city_count,
        "date_range": {
            "from": earliest_dt.isoformat() if earliest_dt else None,
            "to":   latest_dt.isoformat()   if latest_dt   else None,
        },
        "avg_india_aqi":    round(avg_aqi, 1) if avg_aqi else None,
        "category_distribution": {
            cat: cnt for cat, cnt in cat_counts
        },
    }


# ── 5. V2/V3: All India live stations (29 DB cities) ─────────────────────────
@router.get("/india-stations", response_model=List[dict])
def india_stations(db: Session = Depends(get_db)):
    """
    Returns live AQI data for all 29 monitored Indian cities.

    Uses the same direct SQLAlchemy ORM query as /aqi/rankings — fast,
    reliable, no external API calls. Returns data formatted for AQIMap.

    Each entry: name, state, latitude, longitude, india_aqi,
                india_aqi_category, station_name, pm2_5_ugm3, stale, source
    """
    from datetime import datetime, timedelta

    # Subquery: latest reading per station (same pattern as /aqi/rankings)
    latest_sub = (
        db.query(
            AQIData.station_id,
            func.max(AQIData.datetime).label("max_dt"),
        )
        .group_by(AQIData.station_id)
        .subquery()
    )

    rows = (
        db.query(AQIData, City, MonitoringStation)
        .join(MonitoringStation, AQIData.station_id == MonitoringStation.id)
        .join(City, MonitoringStation.city_id == City.id)
        .join(
            latest_sub,
            (AQIData.station_id == latest_sub.c.station_id)
            & (AQIData.datetime == latest_sub.c.max_dt),
        )
        .order_by(City.name)
        .all()
    )

    now_ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
    result = []
    for aqi_row, city_row, ms_row in rows:
        dt = aqi_row.datetime
        stale = (now_ist - dt).total_seconds() > 3 * 3600 if dt else True
        result.append({
            "name":               city_row.name,
            "state":              city_row.state,
            "latitude":           float(city_row.latitude),
            "longitude":          float(city_row.longitude),
            "india_aqi":          float(aqi_row.india_aqi)    if aqi_row.india_aqi    is not None else None,
            "india_aqi_category": aqi_row.india_aqi_category,
            "pm2_5_ugm3":         float(aqi_row.pm2_5_ugm3)   if aqi_row.pm2_5_ugm3   is not None else None,
            "pm10_ugm3":          float(aqi_row.pm10_ugm3)    if aqi_row.pm10_ugm3    is not None else None,
            "no2_ugm3":           float(aqi_row.no2_ugm3)     if aqi_row.no2_ugm3     is not None else None,
            "station_name":       ms_row.station_name or city_row.name.title(),
            "stale":              stale,
            "source":             "db",
        })
    return result


# ── 6. V2: Stations filtered by state ────────────────────────────────────────
@router.get("/by-state", response_model=List[dict])
def stations_by_state(
    state: str = Query(..., description="State name (case-insensitive), e.g. 'Maharashtra'"),
):
    """
    Returns live station data for all cities/stations in the given state.
    Uses the same cached all-India dataset as /india-stations.
    """
    from app.services.data_pipeline import get_all_india_live
    all_stations = get_all_india_live()
    state_lower  = state.strip().lower()
    return [s for s in all_stations if (s.get("state") or "").lower() == state_lower]


# ── 7. Current AQI for one city ───────────────────────────────────────────────
@router.get("/{city_name}/current", response_model=dict)
def city_current(city_name: str, db: Session = Depends(get_db)):
    """Latest AQI reading for the given city (case-insensitive)."""
    city = (
        db.query(City)
        .filter(func.lower(City.name) == city_name.lower())
        .first()
    )
    if not city:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"City '{city_name}' not found. Check GET /aqi/cities for valid names.",
        )

    # Get the station for this city
    station = (
        db.query(MonitoringStation)
        .filter(MonitoringStation.city_id == city.id)
        .first()
    )
    if not station:
        raise HTTPException(status_code=404, detail="No monitoring station for this city.")

    latest = (
        db.query(AQIData)
        .filter(AQIData.station_id == station.id)
        .order_by(desc(AQIData.datetime))
        .first()
    )
    if not latest:
        raise HTTPException(status_code=404, detail="No AQI data found for this city.")

    return _row_to_current(city, latest)


# ── 6. Historical data for one city ──────────────────────────────────────────
@router.get("/{city_name}/history", response_model=dict)
def city_history(
    city_name: str,
    days: int = Query(7, ge=1, le=90, description="Number of past days to return"),
    db: Session = Depends(get_db),
):
    """
    Returns hourly AQI records for the given city over the last `days` days.
    Maximum 90 days (~2,160 rows per city).
    """
    city = (
        db.query(City)
        .filter(func.lower(City.name) == city_name.lower())
        .first()
    )
    if not city:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"City '{city_name}' not found. Check GET /aqi/cities for valid names.",
        )

    station = (
        db.query(MonitoringStation)
        .filter(MonitoringStation.city_id == city.id)
        .first()
    )
    if not station:
        raise HTTPException(status_code=404, detail="No monitoring station for this city.")

    # Always anchor "last N days" to current IST time, not to the last DB row.
    # This ensures the chart covers the real last 7 days even if the pipeline
    # has a small lag (recent hours may simply have no data points yet).
    now_ist   = datetime.utcnow() + timedelta(hours=5, minutes=30)
    latest_dt = now_ist
    cutoff    = now_ist - timedelta(days=days)

    # Verify the city has any data at all
    has_data = (
        db.query(func.count(AQIData.id))
        .filter(AQIData.station_id == station.id)
        .scalar()
    )
    if not has_data:
        raise HTTPException(status_code=404, detail="No AQI data found for this city.")

    records = (
        db.query(AQIData)
        .filter(
            AQIData.station_id == station.id,
            AQIData.datetime >= cutoff,
        )
        .order_by(AQIData.datetime)
        .all()
    )

    def _rec(a: AQIData) -> dict:
        return {
            "datetime":           a.datetime,
            "india_aqi":          a.india_aqi,
            "india_aqi_category": a.india_aqi_category,
            "us_aqi":             a.us_aqi,
            "pm2_5_ugm3":         a.pm2_5_ugm3,
            "pm10_ugm3":          a.pm10_ugm3,
            "no2_ugm3":           a.no2_ugm3,
            "so2_ugm3":           a.so2_ugm3,
            "co_ugm3":            a.co_ugm3,
            "o3_ugm3":            a.o3_ugm3,
            "temperature_c":      a.temperature_c,
            "wind_speed_kmh":     a.wind_speed_kmh,
            "humidity_percent":   a.humidity_percent,
            "season":             a.season,
            "time_of_day":        a.time_of_day,
        }

    return {
        "city":        city.name,
        "state":       city.state,
        "latitude":    city.latitude,
        "longitude":   city.longitude,
        "days":        days,
        "from":        cutoff.isoformat(),
        "to":          latest_dt.isoformat(),
        "record_count": len(records),
        "records":     [_rec(r) for r in records],
    }
