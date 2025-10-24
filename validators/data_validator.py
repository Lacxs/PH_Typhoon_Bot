"""
Data Validator for Typhoon Data
Validates parsed data for sanity and accuracy
"""

from typing import Optional, List, Tuple
import logging

logger = logging.getLogger(__name__)


class DataValidator:
    """Validate parsed typhoon data for accuracy"""

    # Philippine Area of Responsibility (PAR) bounds
    PAR_BOUNDS = {
        'lat_min': 4.0,   # Southern boundary
        'lat_max': 25.0,  # Northern boundary
        'lon_min': 114.0, # Western boundary
        'lon_max': 135.0  # Eastern boundary
    }

    # Expanded monitoring zone (includes "outside PAR but being monitored")
    MONITORING_BOUNDS = {
        'lat_min': 0.0,
        'lat_max': 30.0,
        'lon_min': 110.0,
        'lon_max': 160.0
    }

    @classmethod
    def validate_coordinates(cls, lat: float, lon: float) -> Tuple[bool, str, Optional[str]]:
        """
        Validate latitude and longitude

        Returns:
            (is_valid, location_status, warning_message)
        """
        # Basic validation
        if not (-90 <= lat <= 90):
            return False, 'invalid', f"Invalid latitude: {lat}"
        if not (-180 <= lon <= 180):
            return False, 'invalid', f"Invalid longitude: {lon}"

        # Check if in monitoring zone
        if not (cls.MONITORING_BOUNDS['lat_min'] <= lat <= cls.MONITORING_BOUNDS['lat_max'] and
                cls.MONITORING_BOUNDS['lon_min'] <= lon <= cls.MONITORING_BOUNDS['lon_max']):
            return False, 'out_of_range', f"Coordinates far outside Philippine monitoring area: {lat}°N, {lon}°E"

        # Check if in PAR
        if (cls.PAR_BOUNDS['lat_min'] <= lat <= cls.PAR_BOUNDS['lat_max'] and
            cls.PAR_BOUNDS['lon_min'] <= lon <= cls.PAR_BOUNDS['lon_max']):
            return True, 'inside_par', None

        # Outside PAR but within monitoring zone
        return True, 'outside_par', f"System outside PAR but being monitored: {lat}°N, {lon}°E"

    @staticmethod
    def validate_wind_speed(speed: Optional[int], field_name: str = "wind") -> Tuple[bool, Optional[str]]:
        """Validate wind speed values"""
        if speed is None:
            return True, None  # Optional field

        # Sanity ranges for tropical cyclones
        if speed < 0:
            return False, f"{field_name} speed cannot be negative: {speed}"

        if speed > 350:
            return False, f"{field_name} speed unrealistic: {speed} km/h (max recorded: 305 km/h)"

        if speed > 250:
            # Warn but don't fail - could be a super typhoon
            return True, f"Very high {field_name} speed: {speed} km/h - verify data"

        return True, None

    @staticmethod
    def validate_movement_speed(speed: Optional[int]) -> Tuple[bool, Optional[str]]:
        """Validate typhoon movement speed"""
        if speed is None:
            return True, None  # Stationary systems have no speed

        if speed < 0:
            return False, f"Movement speed cannot be negative: {speed}"

        # Typical typhoon movement: 10-40 km/h
        # Fast-moving typhoons: up to 80 km/h
        if speed > 100:
            return False, f"Movement speed unrealistic: {speed} km/h (typical max: 80 km/h)"

        if speed > 70:
            return True, f"Very fast-moving system: {speed} km/h - verify data"

        return True, None

    @staticmethod
    def validate_direction(direction: Optional[str]) -> Tuple[bool, Optional[str]]:
        """Validate movement direction"""
        if direction is None:
            return True, None

        valid_directions = [
            'N', 'NNE', 'NE', 'ENE',
            'E', 'ESE', 'SE', 'SSE',
            'S', 'SSW', 'SW', 'WSW',
            'W', 'WNW', 'NW', 'NNW',
            'NORTH', 'NORTHEAST', 'EAST', 'SOUTHEAST',
            'SOUTH', 'SOUTHWEST', 'WEST', 'NORTHWEST'
        ]

        direction_upper = direction.upper().replace('WARD', '')

        if direction_upper not in valid_directions:
            return False, f"Invalid direction: {direction}"

        return True, None

    @staticmethod
    def validate_tcws_level(tcws: int) -> Tuple[bool, Optional[str]]:
        """Validate TCWS signal number"""
        if not 1 <= tcws <= 5:
            return False, f"Invalid TCWS level: {tcws} (must be 1-5)"
        return True, None

    @classmethod
    def validate_bulletin(cls, bulletin_data: dict) -> Tuple[bool, List[str], List[str]]:
        """
        Comprehensive validation of bulletin data

        Returns:
            (is_valid, errors, warnings)
        """
        errors = []
        warnings = []

        # Validate coordinates
        lat = bulletin_data.get('latitude')
        lon = bulletin_data.get('longitude')

        if lat is None or lon is None:
            errors.append("Missing coordinates")
        else:
            is_valid, status, message = cls.validate_coordinates(lat, lon)
            if not is_valid:
                errors.append(message)
            elif message:
                warnings.append(message)

        # Validate winds
        max_winds = bulletin_data.get('max_winds')
        is_valid, message = cls.validate_wind_speed(max_winds, "Maximum sustained winds")
        if not is_valid:
            errors.append(message)
        elif message:
            warnings.append(message)

        # Validate gusts
        max_gusts = bulletin_data.get('max_gusts')
        is_valid, message = cls.validate_wind_speed(max_gusts, "Gusts")
        if not is_valid:
            errors.append(message)
        elif message:
            warnings.append(message)

        # Validate gusts > winds (if both present)
        if max_winds and max_gusts and max_gusts < max_winds:
            errors.append(f"Gusts ({max_gusts} km/h) should be higher than sustained winds ({max_winds} km/h)")

        # Validate movement speed
        movement_speed = bulletin_data.get('movement_speed')
        is_valid, message = cls.validate_movement_speed(movement_speed)
        if not is_valid:
            errors.append(message)
        elif message:
            warnings.append(message)

        # Validate direction
        direction = bulletin_data.get('movement_direction')
        is_valid, message = cls.validate_direction(direction)
        if not is_valid:
            errors.append(message)
        elif message:
            warnings.append(message)

        # Validate TCWS areas
        tcws_areas = bulletin_data.get('tcws_areas', {})
        for level in tcws_areas.keys():
            is_valid, message = cls.validate_tcws_level(level)
            if not is_valid:
                errors.append(message)

        # Validate name exists
        if not bulletin_data.get('name') or bulletin_data['name'] == 'Unknown System':
            warnings.append("Cyclone name not found in bulletin")

        # Validate bulletin time
        if not bulletin_data.get('bulletin_time'):
            warnings.append("Bulletin timestamp not found")

        return len(errors) == 0, errors, warnings
