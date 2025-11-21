"""
QRH 检查单库
Quick Reference Handbook
"""

QRH_LIBRARY = {
    "low_oil_pressure": {
        "title": "LOW OIL PRESSURE",
        "items": ["Throttle - REDUCE", "Landing Area - SELECT", "Prepare - FOR ENGINE FAILURE"]
    },
    "engine_fire": {
        "title": "ENGINE FIRE IN FLIGHT",
        "items": ["Mixture - CUTOFF", "Fuel Valve - OFF", "Master Switch - OFF", "Cabin Heat - OFF", "Airspeed - 105 KIAS"]
    },
    "electrical_fire": {
        "title": "ELECTRICAL FIRE",
        "items": ["Master Switch - OFF", "Vents/Cabin Air - CLOSED", "Fire Extinguisher - ACTIVATE", "Avionics - OFF"]
    },
    "carburetor_icing": {
        "title": "CARBURETOR ICING",
        "items": ["Carburetor Heat - FULL ON", "Throttle - OPEN slowly", "Monitor - RPM RECOVERY", "Mixture - ADJUST"]
    },
    "fuel_imbalance": {
        "title": "FUEL IMBALANCE",
        "items": ["Fuel Selector - SWITCH to fuller tank", "Cross-feed - OPEN (if available)", "Monitor - FUEL QTY", "Plan - EARLY LANDING if severe"]
    },
    "vacuum_failure": {
        "title": "VACUUM SYSTEM FAILURE",
        "items": ["Verify - ATTITUDE INDICATOR unreliable", "Use - TURN COORDINATOR for bank", "Refer - MAGNETIC COMPASS", "Avoid - IMC if possible"]
    },
    "alternator_failure": {
        "title": "ALTERNATOR FAILURE",
        "items": ["Alternator - CYCLE (OFF then ON)", "If no recovery - SHED LOAD", "Avionics - MINIMIZE", "Battery - MONITOR voltage", "Plan - NEAREST AIRPORT"]
    }
}
