import requests
from bs4 import BeautifulSoup
import re
import logging

logger = logging.getLogger(__name__)

class PAGASAParser:
    """Parser for PAGASA weather data from the NEW bagong.pagasa.dost.gov.ph site"""
    
    # NEW SITE URLs
    WEATHER_URL = "https://bagong.pagasa.dost.gov.ph/weather"
    METAFILE_URL = "https://pubfiles.pagasa.dost.gov.ph/pagasaweb/files/weather/metafile.txt"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def fetch_weather_data(self):
        """Fetch weather data from PAGASA's NEW website"""
        try:
            logger.info(f"Fetching NEW PAGASA weather page: {self.WEATHER_URL}")
            response = self.session.get(self.WEATHER_URL, timeout=30)
            response.raise_for_status()
            
            logger.info(f"Weather page fetched, length: {len(response.text)} chars")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for the TC Information section
            tc_data = self._parse_tc_table(soup)
            
            if tc_data:
                logger.info(f"Found TC data: {tc_data.get('name', 'Unknown')}")
                return tc_data
            
            # If no TC, check for LPA
            lpa_data = self._parse_lpa_data(soup)
            
            if lpa_data:
                logger.info(f"Found LPA data")
                return lpa_data
            
            logger.info("No active tropical cyclone or LPA found")
            return None
            
        except Exception as e:
            logger.error(f"Error fetching weather data: {e}")
            return None
    
    def _parse_tc_table(self, soup):
        """Parse the Tropical Cyclone table from the new site"""
        try:
            # Find the TC Information section
            tc_section = soup.find('h3', string=re.compile(r'TC Information', re.I))
            
            if not tc_section:
                logger.info("No TC Information section found")
                return None
            
            # Find the table after the TC Information heading
            table = tc_section.find_next('table')
            
            if not table:
                logger.info("No TC table found")
                return None
            
            # Extract all table rows
            rows = table.find_all('tr')
            
            tc_data = {
                'name': None,
                'location': None,
                'lat': None,
                'lon': None,
                'max_winds': None,
                'gustiness': None,
                'movement': None,
                'category': None
            }
            
            for row in rows:
                cells = row.find_all('td')
                if not cells:
                    continue
                
                text = ' '.join(cell.get_text(strip=True) for cell in cells)
                logger.debug(f"Processing row: {text}")
                
                # Parse different fields
                if 'TROPICAL CYCLONE' in text.upper() or 'TROPICAL DEPRESSION' in text.upper():
                    # Extract TC category and name
                    if 'OUTSIDE PAR' in text.upper():
                        tc_data['category'] = 'OUTSIDE PAR'
                    
                    # Try to extract name (usually in parentheses or quotes)
                    name_match = re.search(r'["\']([A-Z]+)["\']|\(([A-Z]+)\)', text)
                    if name_match:
                        tc_data['name'] = name_match.group(1) or name_match.group(2)
                
                elif 'TROPICAL DEPRESSION' in text.upper():
                    tc_data['category'] = 'TROPICAL DEPRESSION'
                
                elif 'LOCATION:' in text.upper():
                    # Extract coordinates
                    coord_match = re.search(r'(\d+\.?\d*)\s*°?\s*([NS])\s*,?\s*(\d+\.?\d*)\s*°?\s*([EW])', text)
                    if coord_match:
                        lat = float(coord_match.group(1))
                        if coord_match.group(2) == 'S':
                            lat = -lat
                        lon = float(coord_match.group(3))
                        if coord_match.group(4) == 'W':
                            lon = -lon
                        
                        tc_data['lat'] = lat
                        tc_data['lon'] = lon
                        tc_data['location'] = text.split('LOCATION:')[1].strip()
                
                elif 'MAXIMUM SUSTAINED WINDS:' in text.upper():
                    wind_match = re.search(r'(\d+)\s*KM/H', text, re.I)
                    if wind_match:
                        tc_data['max_winds'] = int(wind_match.group(1))
                
                elif 'GUSTINESS:' in text.upper():
                    gust_match = re.search(r'(\d+)\s*KM/H', text, re.I)
                    if gust_match:
                        tc_data['gustiness'] = int(gust_match.group(1))
                
                elif 'MOVEMENT:' in text.upper():
                    tc_data['movement'] = text.split('MOVEMENT:')[1].strip()
            
            # Check if we have valid data
            if tc_data['lat'] and tc_data['lon']:
                logger.info(f"Successfully parsed TC: {tc_data}")
                return tc_data
            else:
                logger.warning("TC table found but coordinates missing")
                return None
                
        except Exception as e:
            logger.error(f"Error parsing TC table: {e}")
            return None
    
    def _parse_lpa_data(self, soup):
        """Parse Low Pressure Area data"""
        try:
            # Look for "Low Pressure Area" or "LPA" text
            text = soup.get_text()
            
            if 'low pressure area' not in text.lower() and 'lpa' not in text.lower():
                logger.info("No LPA mentioned on page")
                return None
            
            # Try to extract LPA coordinates
            lpa_pattern = r'(?:Low Pressure Area|LPA)[^\d]*?(\d+\.?\d*)\s*°?\s*([NS])[^\d]*?(\d+\.?\d*)\s*°?\s*([EW])'
            
            match = re.search(lpa_pattern, text, re.I | re.DOTALL)
            
            if match:
                lat = float(match.group(1))
                if match.group(2) == 'S':
                    lat = -lat
                lon = float(match.group(3))
                if match.group(4) == 'W':
                    lon = -lon
                
                logger.info(f"Found LPA at {lat}°N, {lon}°E")
                
                return {
                    'name': 'LPA',
                    'lat': lat,
                    'lon': lon,
                    'category': 'Low Pressure Area'
                }
            
            logger.info("LPA mentioned but coordinates not found")
            return None
            
        except Exception as e:
            logger.error(f"Error parsing LPA data: {e}")
            return None
    
    def fetch_threat_forecast(self):
        """Fetch 5-day TC threat forecast status"""
        try:
            logger.info("Fetching 5-day TC threat forecast...")
            response = self.session.get(self.WEATHER_URL, timeout=30)
            
            # Check if there's any mention of monitoring areas
            if 'being monitored' in response.text.lower() or 'no threat' in response.text.lower():
                logger.info("Threat forecast: Areas being monitored")
                return "Areas being monitored for potential development"
            
            return "No specific threat information available"
            
        except Exception as e:
            logger.error(f"Error fetching threat forecast: {e}")
            return None


# Usage example
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    parser = PAGASAParser()
    data = parser.fetch_weather_data()
    
    if data:
        print(f"Found weather system: {data}")
    else:
        print("No active weather system")
