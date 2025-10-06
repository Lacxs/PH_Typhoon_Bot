"""
PAGASA Severe Weather Bulletin Parser
Fetches and parses official typhoon bulletins and LPA monitoring from PAGASA
"""

import re
import logging
from datetime import datetime
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class PAGASAParser:
    """Parser for PAGASA severe weather bulletins and LPA monitoring"""
    
    PAGASA_BULLETIN_URL = "https://www.pagasa.dost.gov.ph/tropical-cyclone/severe-weather-bulletin"
    PAGASA_METAFILE_URL = "https://pubfiles.pagasa.dost.gov.ph/tamss/weather/metafile.txt"
    PAGASA_WEATHER_URL = "https://www.pagasa.dost.gov.ph/weather"
    PAGASA_LPA_URL = "https://www.pagasa.dost.gov.ph/tropical-cyclone"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def fetch_latest_bulletin(self):
        """
        Fetch the latest PAGASA severe weather bulletin (typhoons + LPAs)
        Returns parsed bulletin data or None if no active system
        """
        try:
            # First check for active tropical cyclones
            data = self._check_tropical_cyclone()
            if data:
                return data
            
            # If no typhoon, check for LPAs
            lpa_data = self._check_low_pressure_area()
            if lpa_data:
                return lpa_data
            
            logger.info("No active tropical cyclone or LPA")
            return None
        
        except Exception as e:
            logger.error(f"Error fetching PAGASA bulletin: {e}")
            return None
    
    def _check_tropical_cyclone(self):
        """Check for active tropical cyclones"""
        try:
            # Try metafile.txt first (faster and more reliable)
            data = self._parse_metafile()
            if data:
                return data
            
            # Fallback to web scraping
            return self._parse_web_bulletin()
        
        except Exception as e:
            logger.warning(f"Tropical cyclone check failed: {e}")
            return None
    
    def _check_low_pressure_area(self):
        """Check for active Low Pressure Areas"""
        try:
            logger.info("Checking for Low Pressure Areas...")
            
            # Check multiple PAGASA pages for LPA information
            urls = [
                self.PAGASA_WEATHER_URL,
                self.PAGASA_LPA_URL,
                self.PAGASA_BULLETIN_URL
            ]
            
            for url in urls:
                try:
                    response = self.session.get(url, timeout=15)
                    response.raise_for_status()
                    
                    soup = BeautifulSoup(response.content, 'html.parser')
                    text = soup.get_text()
                    
                    # Look for LPA mentions
                    lpa_data = self._parse_lpa_from_text(text)
                    if lpa_data:
                        logger.info(f"Found LPA: {lpa_data.get('name', 'Unknown')}")
                        return lpa_data
                
                except Exception as e:
                    logger.debug(f"Could not fetch {url}: {e}")
                    continue
            
            return None
        
        except Exception as e:
            logger.warning(f"LPA check failed: {e}")
            return None
    
    def _parse_lpa_from_text(self, text):
        """Parse LPA information from text"""
        # Look for LPA patterns
        lpa_patterns = [
            r'(?:Low\s+Pressure\s+Area|LPA).*?(?:located|observed|estimated|monitored).*?(\d+\.?\d*)\s*°?\s*N.*?(\d+\.?\d*)\s*°?\s*E',
            r'LPA.*?at\s+(\d+\.?\d*)\s*°?\s*N.*?(\d+\.?\d*)\s*°?\s*E',
        ]
        
        for pattern in lpa_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                lat = float(match.group(1))
                lon = float(match.group(2))
                
                # Extract additional context around the LPA mention
                lpa_context = self._extract_lpa_context(text, match.start())
                
                data = {
                    'source': 'lpa_monitoring',
                    'type': 'Low Pressure Area',
                    'bulletin_time': datetime.now().strftime("%Y-%m-%d %H:%M"),
                    'name': 'LPA',
                    'latitude': lat,
                    'longitude': lon,
                    'movement_direction': self._extract_movement_direction(lpa_context),
                    'movement_speed': self._extract_movement_speed(lpa_context),
                    'max_winds': None,  # LPAs typically don't have sustained winds reported
                    'max_gusts': None,
                    'tcws_areas': {},  # LPAs don't have TCWS
                    'next_bulletin': None,
                    'description': lpa_context[:200]  # First 200 chars of context
                }
                
                return data
        
        return None
    
    def _extract_lpa_context(self, text, position, chars=300):
        """Extract text context around LPA mention"""
        start = max(0, position - chars)
        end = min(len(text), position + chars)
        return text[start:end].strip()
    
    def _parse_metafile(self):
        """Parse PAGASA metafile.txt for quick bulletin access"""
        try:
            response = self.session.get(self.PAGASA_METAFILE_URL, timeout=10)
            response.raise_for_status()
            
            text = response.text
            
            # Check if there's an active tropical cyclone
            if "NO TROPICAL CYCLONE" in text.upper():
                logger.info("No active tropical cyclone reported")
                return None
            
            # Extract cyclone information using regex
            data = {
                'source': 'metafile',
                'type': 'Tropical Cyclone',
                'bulletin_time': self._extract_bulletin_time(text),
                'name': self._extract_cyclone_name(text),
                'latitude': self._extract_latitude(text),
                'longitude': self._extract_longitude(text),
                'movement_direction': self._extract_movement_direction(text),
                'movement_speed': self._extract_movement_speed(text),
                'max_winds': self._extract_max_winds(text),
                'max_gusts': self._extract_max_gusts(text),
                'tcws_areas': self._extract_tcws_areas(text),
                'next_bulletin': self._extract_next_bulletin(text)
            }
            
            # Validate essential fields
            if data['latitude'] and data['longitude'] and data['name']:
                return data
            
            return None
        
        except Exception as e:
            logger.warning(f"Metafile parsing failed: {e}")
            return None
    
    def _parse_web_bulletin(self):
        """Fallback: scrape PAGASA website for bulletin"""
        try:
            response = self.session.get(self.PAGASA_BULLETIN_URL, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find the latest bulletin content
            bulletin_content = soup.find('div', class_='bulletin-content')
            if not bulletin_content:
                bulletin_content = soup.find('article') or soup.find('main')
            
            if not bulletin_content:
                logger.warning("Could not find bulletin content on webpage")
                return None
            
            text = bulletin_content.get_text()
            
            # Check for active cyclone
            if "NO TROPICAL CYCLONE" in text.upper():
                return None
            
            # Parse similar to metafile
            data = {
                'source': 'web',
                'type': 'Tropical Cyclone',
                'bulletin_time': self._extract_bulletin_time(text),
                'name': self._extract_cyclone_name(text),
                'latitude': self._extract_latitude(text),
                'longitude': self._extract_longitude(text),
                'movement_direction': self._extract_movement_direction(text),
                'movement_speed': self._extract_movement_speed(text),
                'max_winds': self._extract_max_winds(text),
                'max_gusts': self._extract_max_gusts(text),
                'tcws_areas': self._extract_tcws_areas(text),
                'next_bulletin': self._extract_next_bulletin(text)
            }
            
            if data['latitude'] and data['longitude'] and data['name']:
                return data
            
            return None
        
        except Exception as e:
            logger.error(f"Web bulletin parsing failed: {e}")
            return None
    
    def _extract_bulletin_time(self, text):
        """Extract bulletin issue time"""
        patterns = [
            r'(\d{1,2}:\d{2}\s*(?:AM|PM))\s+(\d{1,2}\s+\w+\s+\d{4})',
            r'Issued at\s+(\d{1,2}:\d{2}\s*(?:AM|PM))',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)
        return None
    
    def _extract_cyclone_name(self, text):
        """Extract cyclone name"""
        # PAGASA format: "Tropical Depression/Storm/Typhoon NAME"
        patterns = [
            r'(?:TROPICAL\s+(?:DEPRESSION|STORM)|TYPHOON|SUPER\s+TYPHOON)\s+([A-Z]+)',
            r'T[CD]\s+([A-Z]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        return "Unknown"
    
    def _extract_latitude(self, text):
        """Extract latitude"""
        match = re.search(r'(\d+\.?\d*)\s*°?\s*N', text, re.IGNORECASE)
        if match:
            return float(match.group(1))
        return None
    
    def _extract_longitude(self, text):
        """Extract longitude"""
        match = re.search(r'(\d+\.?\d*)\s*°?\s*E', text, re.IGNORECASE)
        if match:
            return float(match.group(1))
        return None
    
    def _extract_movement_direction(self, text):
        """Extract movement direction"""
        patterns = [
            r'moving\s+(\w+(?:\s*-\s*\w+)?)',
            r'(\w+(?:\s*-\s*\w+)?)\s+at\s+\d+\s*km/h'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                direction = match.group(1).upper()
                # Normalize direction
                direction = direction.replace('WARD', '').strip()
                return direction
        return None
    
    def _extract_movement_speed(self, text):
        """Extract movement speed in km/h"""
        match = re.search(r'(\d+)\s*km/h', text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None
    
    def _extract_max_winds(self, text):
        """Extract maximum sustained winds"""
        patterns = [
            r'maximum\s+(?:sustained\s+)?winds?\s+(?:of\s+)?(\d+)\s*km/h',
            r'winds?\s+(?:of\s+)?(\d+)\s*km/h'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None
    
    def _extract_max_gusts(self, text):
        """Extract maximum gust speed"""
        match = re.search(r'gusts?\s+(?:of\s+)?(\d+)\s*km/h', text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None
    
    def _extract_tcws_areas(self, text):
        """Extract TCWS (Tropical Cyclone Wind Signal) areas"""
        tcws_data = {}
        
        # Look for TCWS declarations
        for level in range(1, 6):
            pattern = rf'TCWS\s+#{level}[:\s]+(.*?)(?=TCWS\s+#|$)'
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            
            if match:
                areas_text = match.group(1)
                # Split by common delimiters
                areas = re.split(r'[,;]|\sand\s', areas_text)
                areas = [a.strip() for a in areas if a.strip()]
                tcws_data[level] = areas
        
        return tcws_data
    
    def _extract_next_bulletin(self, text):
        """Extract next bulletin time"""
        patterns = [
            r'next\s+(?:bulletin|update|issue)\s+(?:will\s+be\s+)?(?:at\s+)?(\d{1,2}:\d{2}\s*(?:AM|PM))',
            r'(\d{1,2}:\d{2}\s*(?:AM|PM)).*?(?:today|tomorrow)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None
