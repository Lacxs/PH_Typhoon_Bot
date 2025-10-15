import requests
from bs4 import BeautifulSoup
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class PAGASAParser:
    """Parser for PAGASA weather data from the NEW tropical cyclone bulletin site"""
    
    # UPDATED URLS - Using the new severe weather bulletin page
    BULLETIN_URL = "https://bagong.pagasa.dost.gov.ph/tropical-cyclone/severe-weather-bulletin"
    WEATHER_URL = "https://bagong.pagasa.dost.gov.ph/weather"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def fetch_weather_data(self):
        """Fetch weather data from PAGASA's NEW tropical cyclone bulletin"""
        try:
            logger.info(f"Fetching PAGASA bulletin: {self.BULLETIN_URL}")
            response = self.session.get(self.BULLETIN_URL, timeout=30)
            response.raise_for_status()
            
            logger.info(f"Bulletin page fetched, length: {len(response.text)} chars")
            
            # Save debug copy
            with open('debug_pagasa_bulletin.html', 'w', encoding='utf-8') as f:
                f.write(response.text)
            
            soup = BeautifulSoup(response.text, 'html.parser')
            content = soup.get_text()
            
            # Check if there's an active tropical cyclone
            if 'no tropical cyclone' in content.lower() or len(content.strip()) < 200:
                logger.info("No active tropical cyclone")
                return None
            
            # Parse the bulletin
            tc_data = self._parse_bulletin(soup, content)
            
            if tc_data:
                logger.info(f"Found TC data: {tc_data.get('name', 'Unknown')}")
                return tc_data
            
            logger.info("No active tropical cyclone found in bulletin")
            return None
            
        except Exception as e:
            logger.error(f"Error fetching bulletin: {e}", exc_info=True)
            return None
    
    def _parse_bulletin(self, soup, content):
        """Parse the severe weather bulletin content"""
        try:
            tc_data = {
                'name': None,
                'location': None,
                'lat': None,
                'lon': None,
                'max_winds': None,
                'gustiness': None,
                'movement': None,
                'category': None,
                'issued_time': None,
                'tcws_areas': {}
            }
            
            # Extract cyclone name from heading (e.g., Tropical Depression "Crising")
            heading = soup.find('h1') or soup.find('h2') or soup.find('h3')
            if heading:
                heading_text = heading.get_text(strip=True)
                logger.info(f"Bulletin heading: {heading_text}")
                
                # Extract category (Tropical Depression, Tropical Storm, Typhoon, etc.)
                category_patterns = [
                    r'SUPER TYPHOON',
                    r'SEVERE TROPICAL STORM',
                    r'TROPICAL STORM',
                    r'TROPICAL DEPRESSION',
                    r'TYPHOON'
                ]
                
                for pattern in category_patterns:
                    if re.search(pattern, heading_text, re.I):
                        tc_data['category'] = pattern.replace('_', ' ').title()
                        break
                
                # Extract Philippine name (in quotes)
                name_match = re.search(r'["\']([A-Z][a-z]+)["\']', heading_text)
                if name_match:
                    tc_data['name'] = name_match.group(1)
                else:
                    tc_data['name'] = tc_data['category'] if tc_data['category'] else 'Unknown System'
            
            # Extract issued time
            time_match = re.search(r'Issued at (\d+:\d+\s+[ap]m),\s+(\d+\s+\w+\s+\d{4})', content, re.IGNORECASE)
            if time_match:
                tc_data['issued_time'] = f"{time_match.group(1)}, {time_match.group(2)}"
            
            # Extract location coordinates
            # Pattern: "14.7 °N, 128.4 °E" or similar
            coord_pattern = r'(\d+\.?\d*)\s*°?\s*([NS])\s*,?\s*(\d+\.?\d*)\s*°?\s*([EW])'
            coord_match = re.search(coord_pattern, content)
            
            if coord_match:
                lat = float(coord_match.group(1))
                if coord_match.group(2) == 'S':
                    lat = -lat
                lon = float(coord_match.group(3))
                if coord_match.group(4) == 'W':
                    lon = -lon
                
                tc_data['lat'] = lat
                tc_data['lon'] = lon
                
                # Extract location description
                location_match = re.search(r'(\d+)\s+km\s+([\w\s]+)\s+of\s+([\w\s,]+)', content, re.IGNORECASE)
                if location_match:
                    tc_data['location'] = f"{location_match.group(1)} km {location_match.group(2)} of {location_match.group(3)}"
            
            # Extract movement
            movement_match = re.search(r'Moving\s+([\w\s]+)\s+at\s+(\d+)\s+km/h', content, re.IGNORECASE)
            if movement_match:
                tc_data['movement'] = f"{movement_match.group(1)} at {movement_match.group(2)} km/h"
            
            # Extract wind speed
            wind_match = re.search(r'Maximum sustained winds of\s+(\d+)\s+km/h', content, re.IGNORECASE)
            if wind_match:
                tc_data['max_winds'] = int(wind_match.group(1))
            
            # Extract gustiness
            gust_match = re.search(r'gustiness of up to\s+(\d+)\s+km/h', content, re.IGNORECASE)
            if gust_match:
                tc_data['gustiness'] = int(gust_match.group(1))
            
            # Extract TCWS areas
            tc_data['tcws_areas'] = self._parse_tcws_areas(soup, content)
            
            # Validate we have minimum required data
            if tc_data['lat'] and tc_data['lon']:
                logger.info(f"Successfully parsed bulletin: {tc_data['name']}")
                return tc_data
            else:
                logger.warning("Bulletin found but coordinates missing")
                return None
                
        except Exception as e:
            logger.error(f"Error parsing bulletin: {e}", exc_info=True)
            return None
    
    def _parse_tcws_areas(self, soup, content):
        """Parse Tropical Cyclone Wind Signal areas"""
        tcws_areas = {}
        
        try:
            # Look for Wind Signal section
            # Pattern: "Tropical Cyclone Wind Signal no. 1" or "Wind Signal No. 1"
            signal_sections = re.findall(
                r'(?:Tropical Cyclone )?Wind Signal (?:no\.|No\.) ?(\d+)[:\s]*(.*?)(?=(?:Tropical Cyclone )?Wind Signal|$)',
                content,
                re.IGNORECASE | re.DOTALL
            )
            
            for signal_num, areas_text in signal_sections:
                signal_level = int(signal_num)
                
                # Extract area names (typically comma or newline separated)
                # Clean up the text
                areas_text = re.sub(r'\s+', ' ', areas_text)
                
                # Split by commas, "and", semicolons
                areas = re.split(r'[,;]|\s+and\s+', areas_text)
                
                # Clean and filter areas
                cleaned_areas = []
                for area in areas:
                    area = area.strip()
                    # Remove empty strings and common noise words
                    if area and len(area) > 2 and not area.lower() in ['the', 'of', 'in', 'including']:
                        # Remove parenthetical information for cleaner names
                        area = re.sub(r'\([^)]*\)', '', area).strip()
                        if area:
                            cleaned_areas.append(area)
                
                if cleaned_areas:
                    tcws_areas[signal_level] = cleaned_areas
                    logger.info(f"Found TCWS #{signal_level}: {len(cleaned_areas)} areas")
            
        except Exception as e:
            logger.warning(f"Error parsing TCWS areas: {e}")
        
        return tcws_areas
    
    def fetch_threat_forecast(self):
        """Fetch 5-day TC threat forecast status"""
        try:
            logger.info("Fetching 5-day TC threat forecast...")
            response = self.session.get(self.WEATHER_URL, timeout=30)
            
            content = response.text.lower()
            
            # Check for threat indicators
            if 'being monitored' in content:
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
    
    def fetch_latest_bulletin(self):
        """
        Compatibility wrapper for fetch_weather_data()
        Returns data in the format expected by main.py
        """
        logger.info("fetch_latest_bulletin() called")
        raw_data = self.fetch_weather_data()
        
        if not raw_data:
            return None
        
        # Get the proper system name and type
        system_name = raw_data.get('name', 'Unknown System')
        system_category = raw_data.get('category', 'Tropical Cyclone')
        
        # If no proper name, use the category as the name
        if not system_name or system_name.lower() in ['none', 'unknown']:
            system_name = system_category
        
        # Parse movement if available (e.g., "NORTHWESTWARD AT 35 KM/H")
        movement = raw_data.get('movement', '')
        movement_direction = None
        movement_speed = None
        
        if movement:
            # Extract direction
            direction_match = re.search(r'(NORTH|SOUTH|EAST|WEST|NORTHWEST|NORTHEAST|SOUTHWEST|SOUTHEAST)(?:WARD)?', movement, re.I)
            if direction_match:
                movement_direction = direction_match.group(1).upper()
            
            # Extract speed
            speed_match = re.search(r'(\d+)\s*km/h', movement, re.I)
            if speed_match:
                movement_speed = int(speed_match.group(1))
        
        # Convert to the format main.py expects
        bulletin_data = {
            'name': system_name,
            'latitude': raw_data.get('lat'),
            'longitude': raw_data.get('lon'),
            'bulletin_time': raw_data.get('issued_time') or datetime.now().strftime('%Y-%m-%d %I:%M %p'),
            'type': system_category,
            'movement_direction': movement_direction,
            'movement_speed': movement_speed,
            'max_winds': raw_data.get('max_winds'),
            'max_gusts': raw_data.get('gustiness'),
            'tcws_areas': raw_data.get('tcws_areas', {}),
            'next_bulletin': None,
            'source': 'PAGASA'
        }
        
        logger.info(f"Bulletin data prepared: name={bulletin_data['name']}, type={bulletin_data['type']}, lat={bulletin_data['latitude']}, lon={bulletin_data['longitude']}")
        
        return bulletin_data
    
    def get_bulletin_text(self):
        """Return a text summary of the current weather situation"""
        data = self.fetch_weather_data()
        
        if not data:
            return "No active tropical cyclone"
        
        # Format the data as text
        text_parts = []
        
        if data.get('name'):
            text_parts.append(f"Name: {data['name']}")
        
        if data.get('category'):
            text_parts.append(f"Category: {data['category']}")
        
        if data.get('location'):
            text_parts.append(f"Location: {data['location']}")
        
        if data.get('lat') and data.get('lon'):
            text_parts.append(f"Coordinates: {data['lat']}°N, {data['lon']}°E")
        
        if data.get('max_winds'):
            text_parts.append(f"Max Winds: {data['max_winds']} km/h")
        
        if data.get('gustiness'):
            text_parts.append(f"Gustiness: {data['gustiness']} km/h")
        
        if data.get('movement'):
            text_parts.append(f"Movement: {data['movement']}")
        
        if data.get('issued_time'):
            text_parts.append(f"Issued: {data['issued_time']}")
        
        return "\n".join(text_parts)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    parser = PAGASAParser()
    
    # Test new method
    print("=== Testing Weather Data Fetch ===")
    data = parser.fetch_weather_data()
    if data:
        print(f"Found weather system: {data}")
    else:
        print("No active weather system")
    
    # Test compatibility method
    print("\n=== Testing Compatibility Method ===")
    bulletin = parser.fetch_latest_bulletin()
    print(bulletin)
    
    print("\n=== Testing Bulletin Text ===")
    text = parser.get_bulletin_text()
    print(text)
