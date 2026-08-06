def build_event(cam_id, track_id, event_type, bbox, confidence, timestamp, location, face_match_score=None, matched_db_id=None):
    return {
        "camId": cam_id,
        "trackId": track_id,
        "eventType": event_type,  # "WANTED_PERSON" 또는 "WEAPON"
        "class": "person",
        "bbox": bbox,
        "confidence": confidence,
        "timestamp": timestamp,
        "location": location,
        "isRegisteredTarget": False,
        "targetId": None,
        "roiId": None,
        "meta": {
            "matchedDbId": matched_db_id,
            "faceMatchScore": face_match_score,
        },
        "frameRefBefore": None,
        "frameRefAfter": None,
    }