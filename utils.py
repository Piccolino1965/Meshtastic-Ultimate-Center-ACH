# Funzioni helper complete
# aiutocomputerhelp.it
# Giovanni Popolizio - anon@m00n
###################################


import math
import time
from datetime import datetime
import json

def timestamp():
    return datetime.now().strftime("%H:%M:%S")

def full_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def time_ago(ts):
    if not ts: return ""
    try:
        delta = max(0, int(time.time() - float(ts)))
        if delta < 60: return f"{delta}s"
        if delta < 3600: return f"{delta//60}m"
        if delta < 86400: return f"{delta//3600}h"
        return f"{delta//86400}d"
    except:
        return ""

def haversine_meters(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2): return None
    try:
        r = 6371000.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp, dl = math.radians(lat2-lat1), math.radians(lon2-lon1)
        a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
        return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    except:
        return None

def format_distance(meters):
    if meters is None: return ""
    if meters < 1000: return f"{int(round(meters))} m"
    return f"{meters/1000:.2f} km"

def normalize_id(value):
    if value is None: return None
    if isinstance(value, str): return value.strip()
    try: return f"!{int(value):08x}"
    except: return str(value)

def safe_attr(obj, attr, default=None):
    try:
        return getattr(obj, attr, default)
    except:
        return default

def to_int_or_none(value):
    value = str(value).strip()
    if not value: return None
    try: return int(value)
    except: return None

def get_nested(data, path, default=None):
    try:
        cur = data
        for part in path.split("."):
            if not isinstance(cur, dict): return default
            cur = cur.get(part)
        return cur if cur is not None else default
    except:
        return default

def extract_position(node_dict):
    lat = get_nested(node_dict, "position.latitude")
    lon = get_nested(node_dict, "position.longitude")
    alt = get_nested(node_dict, "position.altitude")
    
    try:
        if lat is not None and lon is not None:
            return float(lat), float(lon), float(alt) if alt else None
    except: pass
    
    lat_i = get_nested(node_dict, "position.latitudeI") or get_nested(node_dict, "position.latitude_i")
    lon_i = get_nested(node_dict, "position.longitudeI") or get_nested(node_dict, "position.longitude_i")
    
    try:
        if lat_i and lon_i:
            return float(lat_i)*1e-7, float(lon_i)*1e-7, float(alt) if alt else None
    except: pass
    
    return None, None, None