"""
JTWC (Joint Typhoon Warning Center) Forecast Parser
Secondary forecast guidance for cross-checking
"""

import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)


class JTWCParser:
    """Parser for JTWC tropical cyclone forecasts"""
    
    JTWC_TEXT_URL = "https://www.metoc.navy.mil/jtwc/products/wp{storm_num}{year}.txt"
    JTWC_KMZ_URL = "https://www.metoc.navy.mil/jtwc/products/wp{storm_num}{year}.kmz"
    JTWC_WEBPAGE = "https://www.metoc.navy.mil/jtwc/jtwc.html"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def fetch_latest_forecast(self, cyclone_name=None):
        """
        Fetch JTWC forecast for the given cyclone
        Returns forecast data or None if not available
        """
        try:
            # Get active systems from JTWC homepage
            active_systems = self._get_active_systems()
            
            if not active_systems:
                logger.info("No active JTWC systems in Western Pacific")
                return None
            
            # Find matching system
            for system in active_systems:
                if cyclone_name and cyclone_name.upper() in system.get('name', '').upper():
                    return self._fetch_system_data(system)
                elif not cyclone_name:
                    # Return first Western Pacific system
                    if system.get('basin') == 'WP':
                        return self._fetch_system_data(system)
            
            logger.warning(f"No matching JTWC system found for {cyclone_name}")
            return None
        
        except Exception as e:
            logger.error(f"Error fetching JTWC forecast: {e}")
            return None
    
    def _get_active_systems(self):
        """Get list of active tropical systems from JTWC"""
        try:
            response = self.session.get(self.JTWC_WEBPAGE, timeout=10)
            response.raise_for_status()
            
            # Parse active systems (simplified - actual implementation would be more robust)
            # JTWC typically lists systems as WP##YEAR (Western Pacific)
            systems = []
            
            # This is a simplified placeholder
            # Real implementation would parse the JTWC RSS feed or webpage
            current_year = datetime.now().year
            
            # Try common storm numbers for current season
            for num in range(1, 40):
                storm_id = f"WP{num:02d}{current_year}"
                if self._check_system_exists(num, current_year):
                    systems.append({
                        'basin': 'WP',
                        'number': num,
                        'year': current_year,
                        'id': storm_id
                    })
            
            return systems
        
        except Exception as e:
            logger.warning(f"Could not fetch active systems: {e}")
            return []
    
    def _check_system_exists(self, storm_num, year):
        """Check if a JTWC advisory exists for this storm number"""
        try:
            url = self.JTWC_TEXT_URL.format(storm_num=f"{storm_num:02d}", year=year)
            response = self.session.head(url, timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def _fetch_system_data(self, system):
        """Fetch detailed forecast data for a specific system"""
        try:
            storm_num = f"{system['number']:02d}"
            year = system['year']
            
            # Fetch text advisory
            text_url = self.JTWC_TEXT_URL.format(storm_num=storm_num, year=year)
            response = self.session.get(text_url, timeout=10)
            response.raise_for_status()
            
            advisory_text = response.text
            
            data = {
                'system_id': system['id'],
                'advisory_text': advisory_text,
                'forecast_positions': self._parse_forecast_positions(advisory_text),
                'kmz_url': self.JTWC_KMZ_URL.format(storm_num=storm_num, year=year)
            }
            
            return data
        
        except Exception as e:
            logger.error(f"Error fetching system data: {e}")
            return None
    
    def _parse_forecast_positions(self, text):
        """Parse forecast positions from JTWC advisory text"""
        import re
        
        positions = []
        
        # JTWC format: "TAU 12: 14.5N 121.2E"
        pattern = r'TAU\s+(\d+):?\s+(\d+\.?\d*)N\s+(\d+\.?\d*)E'
        
        for match in re.finditer(pattern, text):
            tau = int(match.group(1))
            lat = float(match.group(2))
            lon = float(match.group(3))
            
            positions.append({
                'hours': tau,
                'latitude': lat,
                'longitude': lon
            })
        
        return positions
