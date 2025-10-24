"""
Temporal Validator
Validates data consistency over time to detect parsing errors
"""

from typing import Optional, List, Tuple
from datetime import datetime
import logging
import math

logger = logging.getLogger(__name__)


class TemporalValidator:
    """Validate data consistency over time"""

    @staticmethod
    def validate_position_change(
        prev_bulletin: dict,
        curr_bulletin: dict,
        time_diff_hours: float
    ) -> Tuple[bool, List[str]]:
        """
        Check if typhoon movement is realistic

        Returns:
            (is_realistic, warnings)
        """
        warnings = []

        # Get coordinates
        prev_lat = prev_bulletin.get('latitude')
        prev_lon = prev_bulletin.get('longitude')
        curr_lat = curr_bulletin.get('latitude')
        curr_lon = curr_bulletin.get('longitude')

        if None in [prev_lat, prev_lon, curr_lat, curr_lon]:
            return True, []  # Can't validate without coordinates

        # Calculate distance moved using Haversine formula
        distance_km = TemporalValidator._calculate_distance(
            prev_lat, prev_lon, curr_lat, curr_lon
        )

        # Calculate implied speed
        implied_speed = distance_km / time_diff_hours if time_diff_hours > 0 else 0

        # Get declared movement speed
        declared_speed = curr_bulletin.get('movement_speed', 0) or 0

        # Check 1: Impossible speed (>100 km/h)
        if implied_speed > 100:
            warnings.append(
                f"Typhoon moved {distance_km:.0f} km in {time_diff_hours:.1f} hours "
                f"(implied speed: {implied_speed:.0f} km/h) - may indicate parsing error"
            )
            return False, warnings

        # Check 2: Teleportation (moved >200km in <1 hour)
        if time_diff_hours < 1 and distance_km > 200:
            warnings.append(
                f"Typhoon 'jumped' {distance_km:.0f} km in {time_diff_hours*60:.0f} minutes - likely parsing error"
            )
            return False, warnings

        # Check 3: Speed mismatch
        if declared_speed > 0 and implied_speed > 0:
            speed_diff_percent = abs(implied_speed - declared_speed) / declared_speed * 100
            if speed_diff_percent > 50:
                warnings.append(
                    f"Declared speed ({declared_speed} km/h) differs from observed "
                    f"({implied_speed:.0f} km/h) by {speed_diff_percent:.0f}%"
                )

        return True, warnings

    @staticmethod
    def validate_intensity_change(
        prev_bulletin: dict,
        curr_bulletin: dict,
        time_diff_hours: float
    ) -> Tuple[bool, List[str]]:
        """Check if intensity change is realistic"""
        warnings = []

        prev_winds = prev_bulletin.get('max_winds')
        curr_winds = curr_bulletin.get('max_winds')

        if prev_winds is None or curr_winds is None:
            return True, []

        wind_change = curr_winds - prev_winds
        change_per_hour = wind_change / time_diff_hours if time_diff_hours > 0 else 0

        # Rapid intensification: >50 km/h increase in 24 hours
        if time_diff_hours >= 6 and wind_change > 50:
            warnings.append(
                f"Rapid intensification detected: +{wind_change} km/h in {time_diff_hours:.0f} hours"
            )

        # Rapid weakening: >100 km/h decrease in 24 hours
        if time_diff_hours >= 6 and wind_change < -100:
            warnings.append(
                f"Rapid weakening detected: {wind_change} km/h in {time_diff_hours:.0f} hours"
            )

        # Unrealistic change (>20 km/h per hour)
        if abs(change_per_hour) > 20:
            warnings.append(
                f"Unrealistic intensity change: {change_per_hour:.0f} km/h per hour"
            )
            return False, warnings

        return True, warnings

    @staticmethod
    def _calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate distance between two coordinates using Haversine formula
        Returns distance in kilometers
        """
        # Earth radius in kilometers
        R = 6371.0

        # Convert to radians
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)

        # Haversine formula
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))

        return R * c

    @staticmethod
    def estimate_time_difference(prev_bulletin: dict, curr_bulletin: dict) -> float:
        """
        Estimate time difference between bulletins in hours
        Returns default of 3 hours if cannot determine
        """
        # Try to parse bulletin times if available
        # For now, return standard bulletin interval
        return 3.0  # PAGASA typically issues bulletins every 3 hours
