import requests
from bs4 import BeautifulSoup
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class PAGASAParser:
    """Parser for PAGASA weather data from multiple sources"""
    
    # Multiple PAGASA URLs for redundancy
    SEVERE_WEATHER_URL = "https://bagong.pagasa.dost.gov.ph/tropical-cyclone/severe-weather-bulletin"
    SYNOPSIS_URL = "https://www.pagasa.dost.gov.ph/weather"
    ADVISORY_URL = "https://www.pagasa.dost.gov.ph/tropical-cyclone-advisory-iframe"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def fetch_latest_bulletin(self):
        """
        Fetch latest bulletin from multiple PAGASA sources
        Priority: Severe Weather Bulletin > Synopsis > Advisory
        """
        logger.info("fetch_latest_bulletin() called")
        
        # Try Severe Weather Bulletin first (for systems inside PAR)
        bulletin_data = self._fetch_severe_weather_bulletin()
        if bulletin_data:
            logger.info("Got data from Severe Weather Bulletin")
            return bulletin_data
        
        # Try Synopsis page (for LPAs)
        synopsis_data = self._fetch_synopsis()
        if synopsis_data:
            logger.info("Got data from Weather Synopsis")
            return synopsis_data
        
        logger.info("No active weather systems found")
        return None
    
    def _fetch_severe_weather_bulletin(self):
        """Fetch from Severe Weather Bulletin page (systems inside PAR)"""
        try:
            logger.info(f"Fetching PAGASA bulletin: {self.SEVERE_WEATHER_URL}")
            response = self.session.get(self.SEVERE_WEATHER_URL, timeout=30)
            response.raise_for_status()
            
            logger.info(f"Bulletin page fetched, length: {len(response.text)} chars")
            
            # Save debug copy
            try:
                with open('data/debug_pagasa_bulletin.html', 'w', encoding='utf-8') as f:
                    f.write(response.text)
            except:
                pass
            
            soup = BeautifulSoup(response.text, 'html.parser')
            text_content = soup.get_text()
            
            # Check if there's an active tropical cyclone
            if 'no tropical cyclone' in text_content.lower():
                logger.info("No active tropical cyclone (explicit message)")
                return None
            
            # Parse the bulletin
            return self._parse_severe_weather_bulletin(soup, text_content)
            
        except Exception as e:
            logger.error(f"Error fetching severe weather bulletin: {e}")
            return None
    
    def _parse_severe_weather_bulletin(self, soup, content):
        """Parse the severe weather bulletin HTML"""
        try:
            tc_data = {}
            
            # === EXTRACT CYCLONE NAME AND CATEGORY ===
            # Look for the main heading with the cyclone name
            # Pattern: Tropical Depression "Ramil"
            
            # Try multiple selectors for the heading
            name = None
            category = None
            
            # Method 1: Look for text with quotes containing the name
            name_pattern = r'(SUPER TYPHOON|TYPHOON|SEVERE TROPICAL STORM|TROPICAL STORM|TROPICAL DEPRESSION)\s+["\']([A-Z][a-z]+)["\']'
            name_match = re.search(name_pattern, content, re.IGNORECASE)
            
            if name_match:
                category = name_match.group(1).title()
                name = name_match.group(2).capitalize()
                logger.info(f"Found cyclone: {name} ({category})")
            else:
                # Method 2: Look in various heading tags
                for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'div', 'p']):
                    heading_text = heading.get_text(strip=True)
                    
                    # Check for category
                    if re.search(r'TROPICAL DEPRESSION', heading_text, re.I):
                        category = "Tropical Depression"
                    elif re.search(r'TROPICAL STORM', heading_text, re.I):
                        category = "Tropical Storm"
                    elif re.search(r'SEVERE TROPICAL STORM', heading_text, re.I):
                        category = "Severe Tropical Storm"
                    elif re.search(r'TYPHOON', heading_text, re.I):
                        category = "Typhoon"
                    elif re.search(r'SUPER TYPHOON', heading_text, re.I):
                        category = "Super Typhoon"
                    
                    # Check for name in quotes
                    quoted_name = re.search(r'["\']([A-Z][a-z]+)["\']', heading_text)
                    if quoted_name:
                        name = quoted_name.group(1).capitalize()
                    
                    if category or name:
                        logger.info(f"Found in heading: {heading_text}")
                        break
            
            # === EXTRACT COORDINATES ===
            # Pattern: 12.8 °N, 129.5 °E or 12.8°N, 129.5°E
            coord_pattern = r'(\d+\.?\d*)\s*°?\s*([NS])\s*,?\s*(\d+\.?\d*)\s*°?\s*([EW])'
            coord_match = re.search(coord_pattern, content)
            
            latitude = None
            longitude = None
            
            if coord_match:
                latitude = float(coord_match.group(1))
                if coord_match.group(2) == 'S':
                    latitude = -latitude
                longitude = float(coord_match.group(3))
                if coord_match.group(4) == 'W':
                    longitude = -longitude
                logger.info(f"Found coordinates: {latitude}°N, {longitude}°E")
            
            # === EXTRACT WINDS ===
            wind_pattern = r'Maximum sustained winds of\s+(\d+)\s+km/h'
            wind_match = re.search(wind_pattern, content, re.IGNORECASE)
            max_winds = int(wind_match.group(1)) if wind_match else None
            
            # === EXTRACT GUSTS ===
            gust_pattern = r'gustiness of up to\s+(\d+)\s+km/h'
            gust_match = re.search(gust_pattern, content, re.IGNORECASE)
            max_gusts = int(gust_match.group(1)) if gust_match else None
            
            # === EXTRACT MOVEMENT ===
            # Pattern: "Moving Westward" or "Moving West Southwestward"
            movement_pattern = r'Moving\s+((?:North|South|East|West|Northwest|Northeast|Southwest|Southeast)(?:ward)?)'
            movement_match = re.search(movement_pattern, content, re.IGNORECASE)
            movement_direction = movement_match.group(1).upper() if movement_match else None
            
            # Clean up direction (remove "ward")
            if movement_direction:
                movement_direction = movement_direction.replace('WARD', '')
            
            # Try to extract speed if mentioned
            speed_pattern = r'at\s+(\d+)\s+km/h'
            speed_match = re.search(speed_pattern, content, re.IGNORECASE)
            movement_speed = int(speed_match.group(1)) if speed_match else None
            
            # === EXTRACT ISSUED TIME ===
            time_pattern = r'Issued at\s+(\d+:\d+\s+[ap]m),\s+(\d+\s+\w+\s+\d{4})'
            time_match = re.search(time_pattern, content, re.IGNORECASE)
            bulletin_time = f"{time_match.group(1)}, {time_match.group(2)}" if time_match else None
            
            # === EXTRACT TCWS AREAS ===
            tcws_areas = self._parse_tcws_areas(content)
            
            # === VALIDATE DATA ===
            if not latitude or not longitude:
                logger.warning("No coordinates found in bulletin")
                return None
            
            # Build final bulletin data
            bulletin_data = {
                'name': name or category or "Unknown System",
                'type': category,
                'latitude': latitude,
                'longitude': longitude,
                'movement_direction': movement_direction,
                'movement_speed': movement_speed,
                'max_winds': max_winds,
                'max_gusts': max_gusts,
                'bulletin_time': bulletin_time or datetime.now().strftime('%I:%M %p, %d %B %Y'),
                'tcws_areas': tcws_areas,
                'next_bulletin': None,
                'source': 'PAGASA Severe Weather Bulletin'
            }
            
            logger.info(f"Bulletin data prepared: name={bulletin_data['name']}, type={bulletin_data['type']}, lat={bulletin_data['latitude']}, lon={bulletin_data['longitude']}")
            
            return bulletin_data
            
        except Exception as e:
            logger.error(f"Error parsing severe weather bulletin: {e}", exc_info=True)
            return None
    
    def _parse_tcws_areas(self, content):
        """Parse Tropical Cyclone Wind Signal areas"""
        tcws_areas = {}
        
        try:
            # Look for Wind Signal sections
            # Pattern: "Tropical Cyclone Wind Signal no. 1" or "Wind Signal No. 1"
            
            # Find all signal sections
            for signal_num in range(1, 6):  # TCWS 1 through 5
                # Look for this signal number
                pattern = rf'(?:Tropical Cyclone )?Wind Signal (?:no\.|No\.)\s*{signal_num}.*?Affected Areas\s*[:\s]*(.*?)(?=(?:Tropical Cyclone )?Wind Signal|Meteorological Condition|$)'
                match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
                
                if match:
                    areas_text = match.group(1)
                    
                    # Clean up and extract area names
                    # Remove extra whitespace
                    areas_text = re.sub(r'\s+', ' ', areas_text)
                    
                    # Split by common separators
                    areas = re.split(r'[,;]|\s+and\s+', areas_text)
                    
                    # Clean and filter
                    cleaned_areas = []
                    for area in areas:
                        area = area.strip()
                        # Remove parenthetical info
                        area = re.sub(r'\([^)]*\)', '', area).strip()
                        # Filter out noise
                        if area and len(area) > 2 and not area.lower() in ['the', 'of', 'in', 'including', 'rest']:
                            cleaned_areas.append(area)
                    
                    if cleaned_areas:
                        tcws_areas[signal_num] = cleaned_areas
                        logger.info(f"Found TCWS #{signal_num}: {len(cleaned_areas)} areas")
        
        except Exception as e:
            logger.warning(f"Error parsing TCWS areas: {e}")
        
        return tcws_areas
    
    def _fetch_synopsis(self):
        """Fetch from Weather Synopsis page (for LPAs)"""
        try:
            logger.info(f"Fetching weather synopsis: {self.SYNOPSIS_URL}")
            response = self.session.get(self.SYNOPSIS_URL, timeout=30)
            response.raise_for_status()
            
            content = response.text
            soup = BeautifulSoup(content, 'html.parser')
            
            # Look for LPA mentions
            # Pattern: "Low Pressure Area (LPA) was estimated based on all available at 90 km East Northeast of Daet"
            lpa_pattern = r'Low Pressure Area \(LPA\) was estimated.*?at\s+(\d+)\s+km\s+([\w\s]+)\s+of\s+([\w\s,]+)\s*\((\d+\.?\d*)\s*°?\s*([NS])\s*,?\s*(\d+\.?\d*)\s*°?\s*([EW])\)'
            
            lpa_match = re.search(lpa_pattern, content, re.IGNORECASE)
            
            if lpa_match:
                latitude = float(lpa_match.group(4))
                if lpa_match.group(5) == 'S':
                    latitude = -latitude
                    
                longitude = float(lpa_match.group(6))
                if lpa_match.group(7) == 'W':
                    longitude = -longitude
                
                location_desc = f"{lpa_match.group(1)} km {lpa_match.group(2)} of {lpa_match.group(3)}"
                
                logger.info(f"Found LPA: {location_desc}")
                
                return {
                    'name': 'Low Pressure Area',
                    'type': 'Low Pressure Area',
                    'latitude': latitude,
                    'longitude': longitude,
                    'movement_direction': None,
                    'movement_speed': None,
                    'max_winds': None,
                    'max_gusts': None,
                    'bulletin_time': datetime.now().strftime('%I:%M %p, %d %B %Y'),
                    'tcws_areas': {},
                    'next_bulletin': None,
                    'source': 'PAGASA Weather Synopsis'
                }
            
            logger.info("No LPA found in synopsis")
            return None
            
        except Exception as e:
            logger.error(f"Error fetching synopsis: {e}")
            return None
    
    def fetch_threat_forecast(self):
        """Fetch 5-day TC threat forecast status"""
        try:
            logger.info("Fetching 5-day TC threat forecast...")
            response = self.session.get(self.SYNOPSIS_URL, timeout=30)
            
            content = response.text.lower()
            
            # Check for threat indicators
            if 'being monitored' in content or 'lpa' in content:
                return {
                    'has_threat': True,
                    'summary': 'Areas being monitored for potential tropical cyclone development'
                }
            elif 'no threat' in content or 'fair weather' in content:
                return {
                    'has_threat': False,
                    'summary': 'No immediate tropical cyclone threat'
                }
            
            return {
                'has_threat': False,
                'summary': 'Weather conditions normal'
            }
            
        except Exception as e:
            logger.error(f"Error fetching threat forecast: {e}")
            return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    parser = PAGASAParser()
    
    print("=== Testing Bulletin Fetch ===")
    bulletin = parser.fetch_latest_bulletin()
    if bulletin:
        print(f"\nFound: {bulletin['name']} ({bulletin['type']})")
        print(f"Location: {bulletin['latitude']}°N, {bulletin['longitude']}°E")
        print(f"Winds: {bulletin['max_winds']} km/h")
        print(f"Gusts: {bulletin['max_gusts']} km/h")
        print(f"Movement: {bulletin['movement_direction']} at {bulletin['movement_speed']} km/h")
        print(f"TCWS Areas: {bulletin['tcws_areas']}")
    else:
        print("No active weather system found")
