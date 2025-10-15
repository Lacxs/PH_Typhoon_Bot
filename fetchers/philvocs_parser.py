"""
PHILVOCS Earthquake Parser
Fetches and parses earthquake data from PHILVOCS
"""

import requests
from bs4 import BeautifulSoup
import re
import logging
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)


class PHILVOCSParser:
    """Parser for PHILVOCS earthquake data"""
    
    EARTHQUAKE_URL = "https://earthquake.phivolcs.dost.gov.ph/"
    
    # Magnitude threshold for alerts
    ALERT_THRESHOLD = 3.8
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def fetch_recent_earthquakes(self, limit=20):
        """
        Fetch recent earthquake data from PHILVOCS
        Returns list of earthquake dictionaries
        """
        try:
            logger.info(f"Fetching earthquakes from: {self.EARTHQUAKE_URL}")
            
            # Note: PHILVOCS site has SSL issues, so we disable verification
            response = self.session.get(
                self.EARTHQUAKE_URL, 
                timeout=30, 
                verify=False  # PHILVOCS has SSL cert issues
            )
            response.raise_for_status()
            
            logger.info(f"Earthquake page fetched, length: {len(response.text)} chars")
            
            # Save debug copy
            with open('debug_philvocs_page.html', 'w', encoding='utf-8') as f:
                f.write(response.text)
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Parse the earthquake table
            earthquakes = self._parse_earthquake_table(soup)
            
            if earthquakes:
                logger.info(f"Found {len(earthquakes)} earthquakes")
                return earthquakes[:limit]
            else:
                logger.warning("No earthquakes found in table")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching earthquakes: {e}", exc_info=True)
            return []
    
    def _parse_earthquake_table(self, soup):
        """Parse the earthquake table from PHILVOCS page"""
        earthquakes = []
        
        try:
            # PHILVOCS uses a specific table class: "MsoNormalTable"
            table = soup.find('table', {'class': 'MsoNormalTable'})
            
            if not table:
                # Fallback: try to find by looking for the month/year header
                logger.warning("MsoNormalTable not found, trying alternative method...")
                # Look for table that contains "OCTOBER 2025" or similar
                all_tables = soup.find_all('table')
                for t in all_tables:
                    if 'OCTOBER 2025' in t.get_text() or 'Date - Time' in t.get_text():
                        table = t
                        break
            
            if not table:
                logger.warning("Could not find earthquake table")
                return []
            
            logger.info(f"Found earthquake table")
            
            # Parse table rows - PHILVOCS structure has the data in tbody
            tbody = table.find('tbody')
            if tbody:
                rows = tbody.find_all('tr')
            else:
                rows = table.find_all('tr')
            
            logger.info(f"Found {len(rows)} total rows in table")
            
            # The first few rows are headers, skip them
            # Look for rows with actual data (6+ columns)
            data_row_count = 0
            for row in rows:
                cols = row.find_all('td')
                
                # Data rows have 6+ columns: Date-Time, Lat, Lon, Depth, Mag, Location
                if len(cols) >= 6:
                    try:
                        earthquake = self._parse_earthquake_row(cols)
                        if earthquake:
                            earthquakes.append(earthquake)
                            data_row_count += 1
                    except Exception as e:
                        logger.debug(f"Error parsing row: {e}")
                        continue
            
            logger.info(f"Successfully parsed {len(earthquakes)} earthquakes from {data_row_count} data rows")
            
        except Exception as e:
            logger.error(f"Error parsing earthquake table: {e}", exc_info=True)
        
        return earthquakes
    
    def _parse_earthquake_row(self, cols):
        """Parse a single earthquake table row"""
        try:
            # PHILVOCS format: Date-Time | Latitude | Longitude | Depth | Magnitude | Location
            # Extract data from columns
            date_time_str = cols[0].get_text(strip=True)
            latitude_str = cols[1].get_text(strip=True)
            longitude_str = cols[2].get_text(strip=True)
            depth_str = cols[3].get_text(strip=True)
            magnitude_str = cols[4].get_text(strip=True)
            location_str = cols[5].get_text(strip=True) if len(cols) > 5 else 'N/A'
            
            # Skip header rows (they contain text like "Date - Time")
            if 'Date' in date_time_str or 'Time' in date_time_str or 'Philippine' in date_time_str:
                return None
            
            # Parse magnitude (critical field)
            magnitude = self._parse_magnitude(magnitude_str)
            if magnitude is None:
                logger.debug(f"Could not parse magnitude from: {magnitude_str}")
                return None
            
            # Parse coordinates
            latitude = self._parse_coordinate(latitude_str)
            longitude = self._parse_coordinate(longitude_str)
            
            if latitude is None or longitude is None:
                logger.debug(f"Could not parse coordinates: {latitude_str}, {longitude_str}")
                return None
            
            # Parse depth
            depth = self._parse_depth(depth_str)
            
            # Parse datetime
            parsed_datetime = self._parse_datetime(date_time_str)
            
            earthquake = {
                'datetime': parsed_datetime,
                'datetime_str': date_time_str,
                'latitude': latitude,
                'longitude': longitude,
                'depth_km': depth,
                'magnitude': magnitude,
                'location': location_str,
                'source': 'PHILVOCS',
                'is_significant': magnitude >= self.ALERT_THRESHOLD
            }
            
            logger.debug(f"Parsed earthquake: M{magnitude} at {location_str}")
            
            return earthquake
            
        except Exception as e:
            logger.debug(f"Error parsing earthquake row: {e}")
            return None
    
    def _parse_magnitude(self, mag_str):
        """Parse magnitude from string"""
        try:
            # Extract numeric value (e.g., "4.5" from "4.5 ML" or "4.5")
            match = re.search(r'(\d+\.?\d*)', mag_str)
            if match:
                return float(match.group(1))
        except:
            pass
        return None
    
    def _parse_coordinate(self, coord_str):
        """Parse coordinate from string"""
        try:
            # Extract numeric value
            match = re.search(r'(\d+\.?\d*)', coord_str)
            if match:
                return float(match.group(1))
        except:
            pass
        return None
    
    def _parse_depth(self, depth_str):
        """Parse depth from string"""
        try:
            # Extract numeric value (e.g., "10" from "10 km" or "10")
            match = re.search(r'(\d+)', depth_str)
            if match:
                return int(match.group(1))
        except:
            pass
        return None
    
    def _parse_datetime(self, datetime_str):
        """Parse datetime string to datetime object"""
        try:
            # Try common PHILVOCS datetime formats
            formats = [
                '%d %B %Y - %I:%M %p',  # e.g., "15 October 2025 - 09:43 AM"
                '%Y-%m-%d %H:%M:%S',    # e.g., "2025-10-15 09:43:00"
                '%d %b %Y %I:%M %p',    # e.g., "15 Oct 2025 09:43 AM"
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(datetime_str, fmt)
                except ValueError:
                    continue
            
            logger.debug(f"Could not parse datetime: {datetime_str}")
            return None
            
        except Exception as e:
            logger.debug(f"Error parsing datetime: {e}")
            return None
    
    def get_significant_earthquakes(self, hours=24):
        """
        Get significant earthquakes (magnitude >= threshold) in the last N hours
        """
        all_earthquakes = self.fetch_recent_earthquakes(limit=50)
        
        if not all_earthquakes:
            return []
        
        # Filter by significance
        significant = [eq for eq in all_earthquakes if eq['is_significant']]
        
        # Filter by time if datetime available
        if hours:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            significant = [
                eq for eq in significant 
                if eq.get('datetime') and eq['datetime'] >= cutoff_time
            ]
        
        logger.info(f"Found {len(significant)} significant earthquakes (>= {self.ALERT_THRESHOLD})")
        
        return significant
    
    def get_latest_earthquake(self):
        """Get the most recent earthquake"""
        earthquakes = self.fetch_recent_earthquakes(limit=1)
        return earthquakes[0] if earthquakes else None
    
    def format_earthquake_summary(self, earthquake):
        """Format earthquake data as readable text"""
        if not earthquake:
            return "No earthquake data available"
        
        magnitude = earthquake.get('magnitude', 'N/A')
        location = earthquake.get('location', 'Unknown location')
        depth = earthquake.get('depth_km', 'N/A')
        datetime_str = earthquake.get('datetime_str', 'Unknown time')
        
        # Intensity description based on magnitude
        intensity = self._get_intensity_description(magnitude)
        
        summary = f"""🔴 **Magnitude {magnitude} Earthquake**
📍 **Location:** {location}
📅 **Time:** {datetime_str}
📏 **Depth:** {depth} km
💥 **Intensity:** {intensity}
"""
        
        return summary
    
    def _get_intensity_description(self, magnitude):
        """Get intensity description based on magnitude"""
        try:
            mag = float(magnitude)
            if mag >= 7.0:
                return "Major - Severe damage expected"
            elif mag >= 6.0:
                return "Strong - Damage to structures"
            elif mag >= 5.0:
                return "Moderate - Felt widely, minor damage"
            elif mag >= 4.0:
                return "Light - Felt by many, no damage"
            elif mag >= 3.0:
                return "Minor - Felt by some people"
            else:
                return "Micro - Generally not felt"
        except:
            return "Unknown"
    
    def format_earthquake_list(self, earthquakes):
        """Format multiple earthquakes as a list"""
        if not earthquakes:
            return "No recent earthquakes"
        
        lines = [f"📊 **Recent Earthquakes ({len(earthquakes)} found)**\n"]
        
        for i, eq in enumerate(earthquakes[:10], 1):
            mag = eq.get('magnitude', 'N/A')
            loc = eq.get('location', 'Unknown')
            time = eq.get('datetime_str', 'Unknown')
            
            # Truncate location if too long
            if len(loc) > 40:
                loc = loc[:37] + "..."
            
            lines.append(f"{i}. **M{mag}** - {loc}")
            lines.append(f"   📅 {time}")
            
            if i < len(earthquakes):
                lines.append("")  # Blank line between earthquakes
        
        return "\n".join(lines)


if __name__ == "__main__":
    # Disable SSL warnings for testing
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    parser = PHILVOCSParser()
    
    print("=== Testing PHILVOCS Parser ===\n")
    
    # Test 1: Fetch recent earthquakes
    print("[TEST 1] Fetching recent earthquakes...")
    earthquakes = parser.fetch_recent_earthquakes(limit=10)
    
    if earthquakes:
        print(f"✅ Found {len(earthquakes)} earthquakes\n")
        print("Latest earthquake:")
        print(json.dumps(earthquakes[0], indent=2, default=str))
    else:
        print("❌ No earthquakes found")
    
    print("\n" + "="*80 + "\n")
    
    # Test 2: Get significant earthquakes
    print("[TEST 2] Fetching significant earthquakes (>= 3.8)...")
    significant = parser.get_significant_earthquakes(hours=24)
    
    if significant:
        print(f"✅ Found {len(significant)} significant earthquakes in last 24 hours\n")
        for eq in significant:
            print(f"  M{eq['magnitude']} - {eq['location']}")
    else:
        print("✅ No significant earthquakes in last 24 hours")
    
    print("\n" + "="*80 + "\n")
    
    # Test 3: Format earthquake summary
    print("[TEST 3] Formatted earthquake summary...")
    if earthquakes:
        summary = parser.format_earthquake_summary(earthquakes[0])
        print(summary)
    
    print("\n" + "="*80 + "\n")
    
    # Test 4: Format earthquake list
    print("[TEST 4] Formatted earthquake list...")
    if earthquakes:
        eq_list = parser.format_earthquake_list(earthquakes[:5])
        print(eq_list)
    
    print("\n=== Tests Complete ===")
