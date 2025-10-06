"""
Port ETA Calculator
Computes distances and estimated arrival times for typhoon to ports
"""

import logging
from math import radians, cos, sin, asin, sqrt, atan2, degrees

logger = logging.getLogger(__name__)


class PortETACalculator:
    """Calculate distances and ETAs from typhoon to ports"""
    
    EARTH_RADIUS_KM = 6371.0
    PROXIMITY_THRESHOLD_KM = 700  # Extended range for container terminal operations
    
    # Direction mapping for bearing calculation
    DIRECTIONS = {
        'N': 0, 'NNE': 22.5, 'NE': 45, 'ENE': 67.5,
        'E': 90, 'ESE': 112.5, 'SE': 135, 'SSE': 157.5,
        'S': 180, 'SSW': 202.5, 'SW': 225, 'WSW': 247.5,
        'W': 270, 'WNW': 292.5, 'NW': 315, 'NNW': 337.5
    }
    
    def __init__(self, ports):
        """
        Initialize calculator with port locations
        ports: dict of {port_name: (lat, lon)}
        """
        self.ports = ports
    
    def calculate_all_ports(self, lat, lon, movement_dir=None, movement_speed=None, tcws_data=None):
        """
        Calculate status for all ports
        
        Args:
            lat: Typhoon latitude
            lon: Typhoon longitude
            movement_dir: Movement direction (e.g., 'NW', 'N')
            movement_speed: Movement speed in km/h
            tcws_data: Dict of TCWS levels and affected areas
        
        Returns:
            Dict of port statuses
        """
        port_status = {}
        
        for port_name, (port_lat, port_lon) in self.ports.items():
            distance = self.haversine_distance(lat, lon, port_lat, port_lon)
            
            # Determine TCWS level
            tcws_level = self._get_tcws_for_port(port_name, tcws_data) if tcws_data else None
            
            # Calculate ETA
            eta_hours = None
            if movement_dir and movement_speed and movement_speed > 0:
                eta_hours = self.calculate_eta(
                    lat, lon, port_lat, port_lon,
                    movement_dir, movement_speed
                )
            
            # Determine if port is in proximity or has signal
            is_threatened = (tcws_level is not None) or (distance <= self.PROXIMITY_THRESHOLD_KM)
            
            port_status[port_name] = {
                'distance_km': round(distance, 1),
                'tcws': tcws_level,
                'eta_hours': round(eta_hours, 1) if eta_hours else None,
                'is_threatened': is_threatened,
                'in_proximity': distance <= self.PROXIMITY_THRESHOLD_KM
            }
        
        return port_status
    
    def haversine_distance(self, lat1, lon1, lat2, lon2):
        """
        Calculate great-circle distance between two points using Haversine formula
        Returns distance in kilometers
        """
        # Convert to radians
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        
        return self.EARTH_RADIUS_KM * c
    
    def calculate_bearing(self, lat1, lon1, lat2, lon2):
        """
        Calculate initial bearing from point 1 to point 2
        Returns bearing in degrees (0-360)
        """
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        
        dlon = lon2 - lon1
        
        x = sin(dlon) * cos(lat2)
        y = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
        
        bearing = atan2(x, y)
        bearing = degrees(bearing)
        bearing = (bearing + 360) % 360
        
        return bearing
    
    def calculate_eta(self, storm_lat, storm_lon, port_lat, port_lon, movement_dir, movement_speed):
        """
        Calculate ETA from storm to port
        
        Returns:
            Estimated hours until arrival, or None if storm is moving away
        """
        if not movement_dir or not movement_speed or movement_speed <= 0:
            return None
        
        # Get movement bearing
        movement_bearing = self.DIRECTIONS.get(movement_dir.upper())
        if movement_bearing is None:
            logger.warning(f"Unknown direction: {movement_dir}")
            return None
        
        # Calculate bearing from storm to port
        port_bearing = self.calculate_bearing(storm_lat, storm_lon, port_lat, port_lon)
        
        # Calculate angle difference
        angle_diff = abs(movement_bearing - port_bearing)
        if angle_diff > 180:
            angle_diff = 360 - angle_diff
        
        # If storm is moving away (angle > 90°), no ETA
        if angle_diff > 90:
            return None
        
        # Calculate distance
        distance = self.haversine_distance(storm_lat, storm_lon, port_lat, port_lon)
        
        # Project effective speed toward port
        # Using cosine of angle to get component in direction of port
        import math
        effective_speed = movement_speed * math.cos(math.radians(angle_diff))
        
        if effective_speed <= 0:
            return None
        
        # Calculate ETA in hours
        eta = distance / effective_speed
        
        # Only return ETA if reasonable (within 72 hours)
        if eta <= 72:
            return eta
        
        return None
    
    def _get_tcws_for_port(self, port_name, tcws_data):
        """
        Determine TCWS level for a port based on area listings
        
        Args:
            port_name: Name of the port
            tcws_data: Dict of {level: [areas]}
        
        Returns:
            TCWS level (1-5) or None
        """
        if not tcws_data:
            return None
        
        # Check each TCWS level (higher levels first)
        for level in sorted(tcws_data.keys(), reverse=True):
            areas = tcws_data[level]
            
            # Check if port name or surrounding area is mentioned
            for area in areas:
                area_lower = area.lower()
                port_lower = port_name.lower()
                
                # Direct match
                if port_lower in area_lower:
                    return level
                
                # Province/region matching
                # Manila -> Metro Manila, NCR
                if port_lower == 'manila' and any(x in area_lower for x in ['metro manila', 'ncr', 'national capital']):
                    return level
                
                # Subic -> Zambales
                if port_lower == 'subic' and 'zambales' in area_lower:
                    return level
                
                # Batangas -> Batangas province
                if port_lower == 'batangas' and 'batangas' in area_lower:
                    return level
                
                # Iloilo -> Iloilo province/city
                if port_lower == 'iloilo' and 'iloilo' in area_lower:
                    return level
                
                # Cagayan -> Cagayan province/valley
                if port_lower == 'cagayan' and 'cagayan' in area_lower:
                    return level
        
        return None
