"""
PAGASA Severe Weather Bulletin Parser - ENHANCED VERSION
Better support for real metafile format and LPA detection from /weather page
"""

import re
import logging
from datetime import datetime
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class PAGASAParser:
    """Parser for PAGASA severe weather bulletins, LPA monitoring, and threat forecasts"""
    
    PAGASA_BULLETIN_URL = "https://www.pagasa.dost.gov.ph/tropical-cyclone/severe-weather-bulletin"
    PAGASA_METAFILE_URL = "https://pubfiles.pagasa.dost.gov.ph/tamss/weather/metafile.txt"
    PAGASA_WEATHER_URL = "https://www.pagasa.dost.gov.ph/weather"
    PAGASA_LPA_URL = "https://www.pagasa.dost.gov.ph/tropical-cyclone"
    PAGASA_THREAT_URL = "https://www.pagasa.dost.gov.ph/tropical-cyclone/tc-threat-potential-forecast"
    
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
            # Priority 1: Check for active tropical cyclones with coordinates
            data = self._check_tropical_cyclone()
            if data and data.get('latitude') and data.get('longitude'):
                # Valid tropical cyclone with coordinates
                return data
            
            # Priority 2: Check main weather page for LPAs (most reliable)
            lpa_data = self._check_weather_page_lpa()
            if lpa_data:
                return lpa_data
            
            # Priority 3: Check other pages for LPAs (fallback)
            lpa_data = self._check_low_pressure_area()
            if lpa_data:
                return lpa_data
            
            logger.info("No active tropical cyclone or LPA")
            return None
        
        except Exception as e:
            logger.error(f"Error fetching PAGASA bulletin: {e}")
            return None
    
    def _check_weather_page_lpa(self):
        """
        Check the main /weather page for LPAs (PRIMARY METHOD)
        This page clearly shows LPAs with coordinates in a structured format
        """
        try:
            logger.debug("Checking main weather page for LPAs...")
            response = self.session.get(self.PAGASA_WEATHER_URL, timeout=15)
            response.raise_for_status()
            
            text = response.text
            
            # Look for LPA with coordinates in format like:
            # "the Low Pressure Area (LPA) was estimated based on all available at 90 km East Northeast of Daet, Camarines Norte (14.5°N, 123.7°E)"
            lpa_pattern = r'(?:Low\s+Pressure\s+Area|LPA).*?(?:estimated|located|observed).*?at\s+(\d+)\s*km\s+([\w\s]+?)\s+of\s+([\w\s,]+?)\s*\((\d+\.?\d*)\s*°?\s*N,?\s*(\d+\.?\d*)\s*°?\s*E\)'
            
            matches = re.finditer(lpa_pattern, text, re.IGNORECASE | re.DOTALL)
            
            lpas_found = []
            for match in matches:
                distance = match.group(1)
                direction = match.group(2).strip()
                location_name = match.group(3).strip()
                lat = float(match.group(4))
                lon = float(match.group(5))
                
                # Validate coordinates
                if 4.0 <= lat <= 25.0 and 115.0 <= lon <= 135.0:
                    lpas_found.append({
                        'distance': distance,
                        'direction': direction,
                        'location_name': location_name,
                        'latitude': lat,
                        'longitude': lon
                    })
                    logger.info(f"Found LPA: {distance} km {direction} of {location_name} ({lat}°N, {lon}°E)")
            
            if lpas_found:
                # Return the first (usually most significant) LPA
                lpa = lpas_found[0]
                return {
                    'source': 'weather_page',
                    'type': 'Low Pressure Area',
                    'bulletin_time': datetime.now().strftime("%Y-%m-%d %H:%M"),
                    'name': 'LPA',
                    'latitude': lpa['latitude'],
                    'longitude': lpa['longitude'],
                    'movement_direction': None,
                    'movement_speed': None,
                    'max_winds': None,
                    'max_gusts': None,
                    'tcws_areas': {},
                    'next_bulletin': None,
                    'description': f"{lpa['distance']} km {lpa['direction']} of {lpa['location_name']}",
                    'additional_lpas': lpas_found[1:] if len(lpas_found) > 1 else []
                }
            
            return None
        
        except Exception as e:
            logger.warning(f"Weather page LPA check failed: {e}")
            return None
    
    def _check_tropical_cyclone(self):
        """Check for active tropical cyclones"""
        try:
            # Try metafile.txt first (faster and more reliable - official data file)
            data = self._parse_metafile()
            if data and data.get('latitude') and data.get('longitude'):
                # Valid data with coordinates
                return data
            
            # If metafile found TC name but no coordinates, try web scraping
            if data and not (data.get('latitude') and data.get('longitude')):
                logger.info(f"TC '{data.get('name')}' found but no coordinates, trying web scraping...")
                web_data = self._parse_web_bulletin(known_name=data.get('name'))
                if web_data and web_data.get('latitude') and web_data.get('longitude'):
                    return web_data
            
            # No valid TC data, return None to check for LPAs
            return None
        
        except Exception as e:
            logger.warning(f"Tropical cyclone check failed: {e}")
            return None
    
    def _parse_metafile(self):
        """Parse PAGASA metafile.txt - IMPROVED to handle real format"""
        try:
            logger.debug("Fetching metafile.txt...")
            response = self.session.get(self.PAGASA_METAFILE_URL, timeout=10)
            response.raise_for_status()
            
            text = response.text
            logger.debug(f"Metafile fetched, length: {len(text)} chars")
            
            # NEW: Check for TC name in format: PAOLO(MATMO) or NAME(INTERNATIONAL_NAME)
            tc_name_pattern = r'([A-Z]{3,})\s*\(([A-Z]+)\)'
            tc_match = re.search(tc_name_pattern, text)
            
            if tc_match:
                local_name = tc_match.group(1)
                international_name = tc_match.group(2)
                
                # Filter out false positives
                excluded_words = ['WARNING', 'BULLETIN', 'FORECAST', 'ADVISORY', 'SHIPPING']
                if local_name not in excluded_words:
                    logger.info(f"Metafile shows active TC: {local_name} ({international_name})")
                    
                    # Fetch the actual bulletin page for details
                    return self._parse_web_bulletin(known_name=local_name)
            
            # OLD METHOD: Check if there's an active tropical cyclone
            if "NO TROPICAL CYCLONE" in text.upper():
                logger.info("Metafile reports: No active tropical cyclone")
                return None
            
            return None
        
        except Exception as e:
            logger.warning(f"Metafile parsing failed: {e}")
            return None
    
    def _check_low_pressure_area(self):
        """Check for active Low Pressure Areas (FALLBACK METHOD)"""
        try:
            logger.info("Checking for Low Pressure Areas (fallback)...")
            
            # Check multiple PAGASA pages for LPA information
            urls = [
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
            r'(\d+\.?\d*)\s*°?\s*N.*?(\d+\.?\d*)\s*°?\s*E.*?(?:Low\s+Pressure\s+Area|LPA)',
        ]
        
        for pattern in lpa_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                lat = float(match.group(1))
                lon = float(match.group(2))
                
                # Validate coordinates are in reasonable Philippine region
                if not (4.0 <= lat <= 25.0 and 115.0 <= lon <= 135.0):
                    logger.debug(f"Coordinates outside expected region: {lat}°N, {lon}°E")
                    continue
                
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
                    'max_winds': None,
                    'max_gusts': None,
                    'tcws_areas': {},
                    'next_bulletin': None,
                    'description': lpa_context[:200]
                }
                
                return data
        
        return None
    
    def _extract_lpa_context(self, text, position, chars=300):
        """Extract text context around LPA mention"""
        start = max(0, position - chars)
        end = min(len(text), position + chars)
        return text[start:end].strip()
    
    def _parse_web_bulletin(self, known_name=None):
        """Fallback: scrape PAGASA website for bulletin - IMPROVED VERSION"""
        try:
            logger.info("Falling back to web scraping...")
            response = self.session.get(self.PAGASA_BULLETIN_URL, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # IMPROVED: Try multiple selectors in priority order
            bulletin_content = None
            selectors = [
                # Original selectors
                ('div', 'bulletin-content'),
                ('article', None),
                ('main', None),
                # Additional common WordPress/CMS selectors
                ('div', 'entry-content'),
                ('div', 'post-content'),
                ('div', 'content'),
                ('div', 'page-content'),
                ('section', 'content'),
                # Broader fallbacks
                ('div', 'container'),
            ]
            
            for tag, class_name in selectors:
                if class_name:
                    bulletin_content = soup.find(tag, class_=class_name)
                    if bulletin_content:
                        logger.debug(f"Found content using: <{tag} class='{class_name}'>")
                        break
                else:
                    bulletin_content = soup.find(tag)
                    if bulletin_content:
                        logger.debug(f"Found content using: <{tag}>")
                        break
            
            # Ultimate fallback: use body text
            if not bulletin_content:
                logger.warning("No specific content container found, using body text")
                bulletin_content = soup.find('body')
            
            if not bulletin_content:
                logger.error("Could not find bulletin content on webpage")
                return None
            
            text = bulletin_content.get_text()
            logger.debug(f"Extracted text length: {len(text)} chars")
            
            # Check for active cyclone
            if "NO TROPICAL CYCLONE" in text.upper() or "WALA" in text.upper():
                logger.info("Webpage confirms: No active tropical cyclone")
                return None
            
            # Parse similar to metafile
            data = {
                'source': 'web',
                'type': 'Tropical Cyclone',
                'bulletin_time': self._extract_bulletin_time(text),
                'name': known_name or self._extract_cyclone_name(text),
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
                logger.info(f"✓ Web scraping parsed: {data['name']} at {data['latitude']}°N, {data['longitude']}°E")
                return data
            else:
                logger.warning(f"Incomplete web data - Name: {data['name']}, Lat: {data['latitude']}, Lon: {data['longitude']}")
            
            return None
        
        except Exception as e:
            logger.error(f"Web bulletin parsing failed: {e}")
            return None
    
    def _extract_bulletin_time(self, text):
        """Extract bulletin issue time"""
        patterns = [
            r'(\d{1,2}:\d{2}\s*(?:AM|PM))\s+(\d{1,2}\s+\w+\s+\d{4})',
            r'Issued at\s+(\d{1,2}:\d{2}\s*(?:AM|PM))',
            r'(\d{1,2}\s+\w+\s+\d{4}\s+\d{1,2}:\d{2}\s*(?:AM|PM))',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)
        return None
    
    def _extract_cyclone_name(self, text):
        """Extract cyclone name - IMPROVED with better filtering"""
        patterns = [
            r'(?:TROPICAL\s+(?:DEPRESSION|STORM)|TYPHOON|SUPER\s+TYPHOON)\s+"?([A-Z]+)"?',
            r'T[CD]\s+"?([A-Z]+)"?',
            r'(?:named|called)\s+"?([A-Z]+)"?',
        ]
        
        # Words to exclude (false positives)
        excluded_words = [
            'THE', 'AND', 'FOR', 'WITH', 'WARNING', 'BULLETIN', 
            'FORECAST', 'ADVISORY', 'UPDATE', 'ISSUED', 'EFFECTS',
            'AREA', 'PAR', 'RESPONSIBILITY', 'AFFECTING', 'TROPICAL',
            'CYCLONE', 'PHILIPPINE', 'SEVERE', 'WEATHER', 'STORM',
            'DEPRESSION', 'SHIPPING'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).upper()
                # Filter out false positives and ensure name is valid
                if name not in excluded_words and len(name) >= 3:
                    return name
        
        return "Unknown"
    
    def _extract_latitude(self, text):
        """Extract latitude - IMPROVED"""
        patterns = [
            r'(\d+\.?\d*)\s*°?\s*N',
            r'(\d+\.?\d*)\s*degrees?\s*N',
            r'latitude[:\s]+(\d+\.?\d*)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                lat = float(match.group(1))
                # Validate reasonable range for Philippine area
                if 4.0 <= lat <= 25.0:
                    return lat
        return None
    
    def _extract_longitude(self, text):
        """Extract longitude - IMPROVED"""
        patterns = [
            r'(\d+\.?\d*)\s*°?\s*E',
            r'(\d+\.?\d*)\s*degrees?\s*E',
            r'longitude[:\s]+(\d+\.?\d*)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                lon = float(match.group(1))
                # Validate reasonable range for Philippine area
                if 115.0 <= lon <= 135.0:
                    return lon
        return None
    
    def _extract_movement_direction(self, text):
        """Extract movement direction"""
        patterns = [
            r'moving\s+(\w+(?:\s*-\s*\w+)?)',
            r'(\w+(?:\s*-\s*\w+)?)\s+at\s+\d+\s*km/?h',
            r'towards?\s+the\s+(\w+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                direction = match.group(1).upper()
                direction = direction.replace('WARD', '').strip()
                # Validate it's actually a direction
                valid_directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW', 
                                   'NORTH', 'NORTHEAST', 'EAST', 'SOUTHEAST',
                                   'SOUTH', 'SOUTHWEST', 'WEST', 'NORTHWEST',
                                   'NNE', 'ENE', 'ESE', 'SSE', 'SSW', 'WSW', 'WNW', 'NNW']
                if any(d in direction for d in valid_directions):
                    return direction
        return None
    
    def _extract_movement_speed(self, text):
        """Extract movement speed in km/h"""
        match = re.search(r'(\d+)\s*km/?h', text, re.IGNORECASE)
        if match:
            speed = int(match.group(1))
            # Validate reasonable typhoon speed (0-100 km/h movement)
            if 0 <= speed <= 100:
                return speed
        return None
    
    def _extract_max_winds(self, text):
        """Extract maximum sustained winds"""
        patterns = [
            r'maximum\s+(?:sustained\s+)?winds?\s+(?:of\s+)?(\d+)\s*km/?h',
            r'winds?\s+(?:of\s+)?(\d+)\s*km/?h',
            r'max\s+winds?[:\s]+(\d+)\s*km/?h',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                winds = int(match.group(1))
                # Validate reasonable wind speed (30-300 km/h for cyclones)
                if 30 <= winds <= 300:
                    return winds
        return None
    
    def _extract_max_gusts(self, text):
        """Extract maximum gust speed"""
        match = re.search(r'gusts?\s+(?:of\s+)?(\d+)\s*km/?h', text, re.IGNORECASE)
        if match:
            gusts = int(match.group(1))
            # Validate reasonable gust speed (40-400 km/h)
            if 40 <= gusts <= 400:
                return gusts
        return None
    
    def _extract_tcws_areas(self, text):
        """Extract TCWS (Tropical Cyclone Wind Signal) areas"""
        tcws_data = {}
        
        for level in range(1, 6):
            patterns = [
                rf'TCWS\s+#{level}[:\s]+(.*?)(?=TCWS\s+#|$)',
                rf'Signal\s+(?:No\.?\s*)?{level}[:\s]+(.*?)(?=Signal\s+(?:No\.?\s*)?\d|$)',
                rf'Wind\s+Signal\s+{level}[:\s]+(.*?)(?=Wind\s+Signal\s+\d|$)',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                if match:
                    areas_text = match.group(1)
                    areas = re.split(r'[,;]|\sand\s', areas_text)
                    areas = [a.strip() for a in areas if a.strip() and len(a.strip()) > 2]
                    if areas:
                        tcws_data[level] = areas
                        break
        
        return tcws_data
    
    def _extract_next_bulletin(self, text):
        """Extract next bulletin time"""
        patterns = [
            r'next\s+(?:bulletin|update|issue|advisory)\s+(?:will\s+be\s+)?(?:at\s+)?(\d{1,2}:\d{2}\s*(?:AM|PM))',
            r'(\d{1,2}:\d{2}\s*(?:AM|PM)).*?(?:today|tomorrow)',
            r'next\s+(\d{1,2}\s*(?:AM|PM))',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None
    
    def fetch_threat_forecast(self):
        """
        Fetch PAGASA 5-day TC Threat Potential Forecast
        Returns forecast data or None if unavailable
        """
        try:
            logger.info("Fetching 5-day TC threat forecast...")
            
            response = self.session.get(self.PAGASA_THREAT_URL, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            text = soup.get_text()
            
            forecast_data = {
                'has_threat': False,
                'areas': [],
                'summary': None
            }
            
            threat_keywords = [
                'high', 'medium', 'moderate', 'low',
                'tropical cyclone formation', 'development',
                'invest', 'disturbance', 'area of concern'
            ]
            
            text_lower = text.lower()
            
            for keyword in threat_keywords:
                if keyword in text_lower:
                    forecast_data['has_threat'] = True
                    break
            
            if not forecast_data['has_threat']:
                if any(phrase in text_lower for phrase in ['no areas', 'no tropical cyclone', 'none identified']):
                    forecast_data['summary'] = "No areas of concern identified"
                    return forecast_data
            
            probability_pattern = r'(high|medium|moderate|low)\s+(?:probability|chance|potential|risk)'
            matches = re.finditer(probability_pattern, text_lower, re.IGNORECASE)
            
            probabilities_found = []
            for match in matches:
                level = match.group(1).upper()
                if level == 'MODERATE':
                    level = 'MEDIUM'
                probabilities_found.append(level)
            
            location_patterns = [
                r'(\d+)\s*km\s+(east|west|north|south|northeast|northwest|southeast|southwest)\s+of\s+([A-Za-z\s]+)',
                r'(eastern|western|northern|southern)\s+([A-Za-z\s]+)',
                r'near\s+([A-Za-z\s]+)',
            ]
            
            locations = []
            for pattern in location_patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    locations.append(match.group(0))
            
            timeframe_pattern = r'(\d+)[\s-]*(?:to[\s-]*)?(\d+)?\s*(?:day|hour)'
            timeframe_match = re.search(timeframe_pattern, text_lower)
            timeframe = None
            if timeframe_match:
                if timeframe_match.group(2):
                    timeframe = f"{timeframe_match.group(1)}-{timeframe_match.group(2)} days"
                else:
                    timeframe = f"{timeframe_match.group(1)} days"
            
            if probabilities_found and locations:
                highest_prob = probabilities_found[0] if probabilities_found else 'UNKNOWN'
                primary_location = locations[0] if locations else 'Western Pacific'
                
                forecast_data['areas'].append({
                    'location': primary_location,
                    'probability': highest_prob,
                    'timeframe': timeframe or '3-5 days'
                })
                
                forecast_data['summary'] = f"{highest_prob} probability - {primary_location}"
            
            elif probabilities_found:
                highest_prob = probabilities_found[0]
                forecast_data['summary'] = f"{highest_prob} formation potential in Western Pacific"
                forecast_data['areas'].append({
                    'location': 'Western Pacific',
                    'probability': highest_prob,
                    'timeframe': timeframe or '3-5 days'
                })
            
            elif forecast_data['has_threat']:
                forecast_data['summary'] = "Areas being monitored for potential development"
            
            else:
                forecast_data['summary'] = "No significant threats identified"
            
            return forecast_data
        
        except Exception as e:
            logger.warning(f"Could not fetch threat forecast: {e}")
            return {
                'has_threat': False,
                'areas': [],
                'summary': None
            }
