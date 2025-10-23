# Data Verification Strategy for PAGASA Scraper

## Current State Assessment

### What's Already In Place ✅
1. **Debug HTML saving** - Raw HTML saved to `data/debug_pagasa_bulletin.html`
2. **Basic coordinate validation** - Checks if lat/lon exist (line 174-176 in pagasa_parser.py)
3. **Test script** - `test_pagasa.py` for manual verification
4. **Logging** - Detailed logging of parsed values

### What's Missing ❌
1. **No sanity checks** - Coordinates, wind speed, movement speed not validated
2. **No cross-validation** - PAGASA vs JTWC data not compared
3. **No historical comparison** - Can't detect if typhoon "jumped" 1000km
4. **No unit tests** - No automated tests with known good data
5. **No alert on parsing failures** - Silent failures in regex matching

---

## Verification Strategy - 5 Layers of Defense

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Input Validation (Raw HTML)                        │
│ - Check HTTP status, content length, expected patterns      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: Parsed Data Sanity Checks                          │
│ - Validate ranges, data types, required fields              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: Cross-Source Validation                            │
│ - Compare PAGASA vs JTWC, check consistency                 │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 4: Temporal Consistency Checks                        │
│ - Compare with previous bulletin, detect anomalies          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 5: Unit Tests with Known Data                         │
│ - Automated tests with archived real bulletins              │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Guide

### Layer 1: Input Validation

Create a validator for raw HTML before parsing:

```python
# validators/input_validator.py

class HTMLValidator:
    """Validate raw HTML before parsing"""

    @staticmethod
    def validate_pagasa_bulletin(html_content: str) -> dict:
        """
        Validate PAGASA bulletin HTML

        Returns:
            dict with 'valid' (bool), 'issues' (list), 'confidence_score' (0-100)
        """
        issues = []
        confidence = 100

        # Check 1: Minimum content length
        if len(html_content) < 1000:
            issues.append("HTML too short - page may not have loaded")
            confidence -= 30

        # Check 2: Look for expected markers
        expected_markers = [
            ('Severe Weather Bulletin', 20),
            ('Tropical Cyclone', 15),
            ('PAGASA', 15),
            ('°N', 10),
            ('°E', 10),
            ('km/h', 10)
        ]

        for marker, penalty in expected_markers:
            if marker.lower() not in html_content.lower():
                issues.append(f"Missing expected marker: '{marker}'")
                confidence -= penalty

        # Check 3: Detect "no active cyclone" message
        if 'no tropical cyclone' in html_content.lower():
            return {
                'valid': True,
                'issues': ['No active tropical cyclone (expected)'],
                'confidence_score': 100,
                'has_active_system': False
            }

        # Check 4: Detect error pages
        error_indicators = ['404', 'not found', 'error', 'unavailable']
        for indicator in error_indicators:
            if indicator in html_content.lower()[:500]:  # Check first 500 chars
                issues.append(f"Possible error page detected: '{indicator}'")
                confidence -= 40

        return {
            'valid': confidence >= 50,
            'issues': issues,
            'confidence_score': confidence,
            'has_active_system': True
        }
```

**Usage:**
```python
# In pagasa_parser.py
response = self.session.get(self.SEVERE_WEATHER_URL, timeout=30)
validation = HTMLValidator.validate_pagasa_bulletin(response.text)

if not validation['valid']:
    logger.error(f"HTML validation failed: {validation['issues']}")
    logger.error(f"Confidence: {validation['confidence_score']}%")
    return None

if not validation['has_active_system']:
    logger.info("No active system (confirmed)")
    return None
```

---

### Layer 2: Parsed Data Sanity Checks

Create comprehensive validators for all parsed fields:

```python
# validators/data_validator.py

from typing import Optional, List, Tuple
import logging

logger = logging.getLogger(__name__)

class DataValidator:
    """Validate parsed typhoon data"""

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
    def validate_coordinates(cls, lat: float, lon: float) -> Tuple[bool, str, str]:
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
            return True, f"⚠️ Very high {field_name} speed: {speed} km/h - verify data"

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
            return True, f"⚠️ Very fast-moving system: {speed} km/h - verify data"

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
```

**Usage:**
```python
# In pagasa_parser.py, after parsing
is_valid, errors, warnings = DataValidator.validate_bulletin(bulletin_data)

if not is_valid:
    logger.error(f"Data validation failed: {errors}")
    # Save debug info
    with open('data/failed_validation.json', 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'errors': errors,
            'warnings': warnings,
            'data': bulletin_data
        }, f, indent=2)
    return None

if warnings:
    for warning in warnings:
        logger.warning(f"Data validation warning: {warning}")
```

---

### Layer 3: Cross-Source Validation

Compare PAGASA and JTWC data when both are available:

```python
# validators/cross_validator.py

from typing import Optional, Dict
import logging
from math import sqrt

logger = logging.getLogger(__name__)

class CrossValidator:
    """Cross-validate data from multiple sources"""

    @staticmethod
    def compare_coordinates(
        pagasa_lat: float, pagasa_lon: float,
        jtwc_lat: float, jtwc_lon: float,
        tolerance_km: float = 100
    ) -> Tuple[bool, float, Optional[str]]:
        """
        Compare coordinates from PAGASA and JTWC

        Returns:
            (is_consistent, distance_km, warning_message)
        """
        # Calculate distance using simple approximation
        # (accurate enough for verification purposes)
        lat_diff = abs(pagasa_lat - jtwc_lat) * 111  # 1 degree ≈ 111 km
        lon_diff = abs(pagasa_lon - jtwc_lon) * 111 * 0.9  # Adjust for latitude
        distance = sqrt(lat_diff**2 + lon_diff**2)

        if distance > tolerance_km:
            warning = f"Coordinates differ by {distance:.0f} km (PAGASA: {pagasa_lat}°N {pagasa_lon}°E, JTWC: {jtwc_lat}°N {jtwc_lon}°E)"
            return False, distance, warning

        return True, distance, None

    @staticmethod
    def compare_intensity(
        pagasa_winds: Optional[int],
        jtwc_winds: Optional[int],
        tolerance_percent: float = 20
    ) -> Tuple[bool, Optional[str]]:
        """
        Compare wind intensity from PAGASA and JTWC

        Returns:
            (is_consistent, warning_message)
        """
        if pagasa_winds is None or jtwc_winds is None:
            return True, None  # Can't compare if missing

        # Calculate percentage difference
        avg = (pagasa_winds + jtwc_winds) / 2
        diff_percent = abs(pagasa_winds - jtwc_winds) / avg * 100

        if diff_percent > tolerance_percent:
            warning = f"Wind intensity differs by {diff_percent:.0f}% (PAGASA: {pagasa_winds} km/h, JTWC: {jtwc_winds} km/h)"
            return False, warning

        return True, None

    @classmethod
    def validate_pagasa_vs_jtwc(
        cls,
        pagasa_data: dict,
        jtwc_data: Optional[dict]
    ) -> Dict[str, any]:
        """
        Comprehensive cross-validation

        Returns:
            Validation report with issues and confidence score
        """
        if jtwc_data is None:
            return {
                'validated': False,
                'reason': 'JTWC data not available',
                'confidence': 70,  # Lower confidence without cross-validation
                'issues': []
            }

        issues = []
        confidence = 100

        # Compare coordinates
        pagasa_lat = pagasa_data.get('latitude')
        pagasa_lon = pagasa_data.get('longitude')

        # JTWC latest position (from forecast_positions)
        jtwc_positions = jtwc_data.get('forecast_positions', [])
        if jtwc_positions:
            jtwc_current = jtwc_positions[0]  # TAU 0

            is_consistent, distance, warning = cls.compare_coordinates(
                pagasa_lat, pagasa_lon,
                jtwc_current['latitude'], jtwc_current['longitude']
            )

            if not is_consistent:
                issues.append(warning)
                confidence -= 20

        # Compare intensity (if available)
        # Note: JTWC uses knots, PAGASA uses km/h
        # Would need conversion here

        return {
            'validated': True,
            'confidence': confidence,
            'issues': issues,
            'distance_diff_km': distance if 'distance' in locals() else None
        }
```

---

### Layer 4: Temporal Consistency Checks

Detect anomalies by comparing with previous bulletin:

```python
# validators/temporal_validator.py

from typing import Optional, List
from datetime import datetime
import json
from pathlib import Path

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

        # Calculate distance moved
        lat_diff = abs(curr_lat - prev_lat) * 111
        lon_diff = abs(curr_lon - prev_lon) * 111 * 0.9
        distance_km = (lat_diff**2 + lon_diff**2)**0.5

        # Calculate implied speed
        implied_speed = distance_km / time_diff_hours if time_diff_hours > 0 else 0

        # Get declared movement speed
        declared_speed = curr_bulletin.get('movement_speed', 0) or 0

        # Check 1: Impossible speed (>100 km/h)
        if implied_speed > 100:
            warnings.append(
                f"⚠️ Typhoon moved {distance_km:.0f} km in {time_diff_hours:.1f} hours "
                f"(implied speed: {implied_speed:.0f} km/h) - may indicate parsing error"
            )
            return False, warnings

        # Check 2: Teleportation (moved >200km in <1 hour)
        if time_diff_hours < 1 and distance_km > 200:
            warnings.append(
                f"⚠️ Typhoon 'jumped' {distance_km:.0f} km in {time_diff_hours*60:.0f} minutes - likely parsing error"
            )
            return False, warnings

        # Check 3: Speed mismatch
        if declared_speed > 0 and implied_speed > 0:
            speed_diff_percent = abs(implied_speed - declared_speed) / declared_speed * 100
            if speed_diff_percent > 50:
                warnings.append(
                    f"ℹ️ Declared speed ({declared_speed} km/h) differs from observed "
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
                f"ℹ️ Rapid intensification detected: +{wind_change} km/h in {time_diff_hours:.0f} hours"
            )

        # Rapid weakening: >100 km/h decrease in 24 hours
        if time_diff_hours >= 6 and wind_change < -100:
            warnings.append(
                f"ℹ️ Rapid weakening detected: {wind_change} km/h in {time_diff_hours:.0f} hours"
            )

        # Unrealistic change (>20 km/h per hour)
        if abs(change_per_hour) > 20:
            warnings.append(
                f"⚠️ Unrealistic intensity change: {change_per_hour:.0f} km/h per hour"
            )
            return False, warnings

        return True, warnings
```

---

### Layer 5: Unit Tests with Known Data

Create tests using real archived bulletins:

```python
# tests/test_pagasa_parser_accuracy.py

import unittest
import json
from pathlib import Path
from fetchers.pagasa_parser import PAGASAParser

class TestPAGASAParserAccuracy(unittest.TestCase):
    """Test parser accuracy with known good data"""

    def setUp(self):
        self.parser = PAGASAParser()
        self.test_data_dir = Path(__file__).parent / 'test_data'

    def test_parse_bulletin_kristine(self):
        """Test parsing of known bulletin (Tropical Storm Kristine)"""

        # Load saved HTML from real bulletin
        with open(self.test_data_dir / 'kristine_bulletin_2024.html', 'r') as f:
            html_content = f.read()

        # Expected values (verified manually)
        expected = {
            'name': 'Kristine',
            'type': 'Tropical Storm',
            'latitude': 14.8,
            'longitude': 121.2,
            'max_winds': 85,
            'max_gusts': 105,
            'movement_direction': 'WEST',
            'movement_speed': 20
        }

        # Parse
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        result = self.parser._parse_severe_weather_bulletin(soup, html_content)

        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(result['name'], expected['name'])
        self.assertEqual(result['type'], expected['type'])
        self.assertAlmostEqual(result['latitude'], expected['latitude'], places=1)
        self.assertAlmostEqual(result['longitude'], expected['longitude'], places=1)
        self.assertEqual(result['max_winds'], expected['max_winds'])
        self.assertEqual(result['max_gusts'], expected['max_gusts'])

    def test_parse_bulletin_with_tcws(self):
        """Test TCWS parsing accuracy"""

        with open(self.test_data_dir / 'bulletin_with_tcws.html', 'r') as f:
            html_content = f.read()

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        result = self.parser._parse_severe_weather_bulletin(soup, html_content)

        # Verify TCWS data was parsed
        self.assertIn('tcws_areas', result)
        tcws = result['tcws_areas']

        # Check if expected areas are in correct signal levels
        # (Values based on the specific test bulletin)
        self.assertIn(1, tcws)  # Signal #1 should exist
        self.assertTrue(len(tcws[1]) > 0)  # Should have areas

    def test_coordinate_validation(self):
        """Test that parsed coordinates are in valid range"""

        # Test multiple bulletins
        for bulletin_file in self.test_data_dir.glob('*.html'):
            with open(bulletin_file, 'r') as f:
                html_content = f.read()

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            result = self.parser._parse_severe_weather_bulletin(soup, html_content)

            if result:
                # Coordinates should be in Philippine region
                self.assertTrue(0 <= result['latitude'] <= 30,
                              f"Latitude {result['latitude']} out of range in {bulletin_file}")
                self.assertTrue(110 <= result['longitude'] <= 160,
                              f"Longitude {result['longitude']} out of range in {bulletin_file}")

if __name__ == '__main__':
    unittest.main()
```

**Create test data archive:**
```bash
# Create directory for test data
mkdir -p tests/test_data

# Save known good bulletins for testing
# (You would manually verify these and save them)
```

---

## Automated Verification Tool

Create a comprehensive verification script:

```python
# verify_data.py

"""
Comprehensive data verification tool
Run this after each bulletin fetch to verify accuracy
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from validators.input_validator import HTMLValidator
from validators.data_validator import DataValidator
from validators.cross_validator import CrossValidator
from validators.temporal_validator import TemporalValidator

logger = logging.getLogger(__name__)

class DataVerificationReport:
    """Generate comprehensive verification report"""

    def __init__(self):
        self.timestamp = datetime.now()
        self.checks_passed = 0
        self.checks_failed = 0
        self.warnings = []
        self.errors = []
        self.confidence_score = 100

    def verify_bulletin(self, bulletin_data: dict, jtwc_data: dict = None) -> dict:
        """Run all verification checks"""

        print("\n" + "="*80)
        print("DATA VERIFICATION REPORT")
        print("="*80)
        print(f"Timestamp: {self.timestamp.isoformat()}")
        print(f"Bulletin: {bulletin_data.get('name')} ({bulletin_data.get('type')})")
        print()

        # Check 1: Data Validation
        print("[CHECK 1] Data Sanity Validation")
        print("-" * 80)

        is_valid, errors, warnings = DataValidator.validate_bulletin(bulletin_data)

        if is_valid:
            self.checks_passed += 1
            print("✅ PASSED - All data within expected ranges")
        else:
            self.checks_failed += 1
            self.errors.extend(errors)
            self.confidence_score -= 20
            print(f"❌ FAILED - {len(errors)} error(s)")
            for error in errors:
                print(f"   - {error}")

        if warnings:
            self.warnings.extend(warnings)
            print(f"⚠️  {len(warnings)} warning(s):")
            for warning in warnings:
                print(f"   - {warning}")
        print()

        # Check 2: Cross-source validation
        if jtwc_data:
            print("[CHECK 2] PAGASA vs JTWC Cross-Validation")
            print("-" * 80)

            cross_val = CrossValidator.validate_pagasa_vs_jtwc(bulletin_data, jtwc_data)

            if cross_val['validated'] and not cross_val['issues']:
                self.checks_passed += 1
                print(f"✅ PASSED - Data consistent (confidence: {cross_val['confidence']}%)")
            else:
                if cross_val['issues']:
                    self.warnings.extend(cross_val['issues'])
                    print(f"⚠️  WARNING - {len(cross_val['issues'])} inconsistency(ies):")
                    for issue in cross_val['issues']:
                        print(f"   - {issue}")
                    self.confidence_score = min(self.confidence_score, cross_val['confidence'])
            print()

        # Check 3: Temporal consistency
        cache_file = Path("data/last_bulletin.json")
        if cache_file.exists():
            print("[CHECK 3] Temporal Consistency Check")
            print("-" * 80)

            with open(cache_file) as f:
                prev_bulletin = json.load(f)

            # Estimate time difference (simplified)
            time_diff_hours = 3  # Assume 3-hour bulletin cycle

            is_realistic, temp_warnings = TemporalValidator.validate_position_change(
                prev_bulletin, bulletin_data, time_diff_hours
            )

            if is_realistic:
                self.checks_passed += 1
                print("✅ PASSED - Movement is realistic")
            else:
                self.checks_failed += 1
                self.confidence_score -= 15
                print("❌ FAILED - Unrealistic movement detected")

            if temp_warnings:
                self.warnings.extend(temp_warnings)
                for warning in temp_warnings:
                    print(f"   {warning}")
            print()

        # Summary
        print("="*80)
        print("VERIFICATION SUMMARY")
        print("="*80)
        print(f"Checks Passed: {self.checks_passed}")
        print(f"Checks Failed: {self.checks_failed}")
        print(f"Warnings: {len(self.warnings)}")
        print(f"Confidence Score: {self.confidence_score}%")

        if self.confidence_score >= 90:
            print("\n✅ DATA QUALITY: EXCELLENT")
        elif self.confidence_score >= 70:
            print("\n⚠️  DATA QUALITY: GOOD (some warnings)")
        elif self.confidence_score >= 50:
            print("\n⚠️  DATA QUALITY: FAIR (multiple issues)")
        else:
            print("\n❌ DATA QUALITY: POOR (manual verification recommended)")

        print("="*80)

        # Return report
        return {
            'timestamp': self.timestamp.isoformat(),
            'confidence_score': self.confidence_score,
            'checks_passed': self.checks_passed,
            'checks_failed': self.checks_failed,
            'errors': self.errors,
            'warnings': self.warnings,
            'recommendation': 'accept' if self.confidence_score >= 70 else 'review'
        }

# Example usage
if __name__ == "__main__":
    from fetchers.pagasa_parser import PAGASAParser

    parser = PAGASAParser()
    bulletin = parser.fetch_latest_bulletin()

    if bulletin:
        verifier = DataVerificationReport()
        report = verifier.verify_bulletin(bulletin)

        # Save report
        with open('data/verification_report.json', 'w') as f:
            json.dump(report, f, indent=2)
```

---

## Monitoring & Alerting

Add alerts when verification fails:

```python
# In main.py, after fetching bulletin

from verify_data import DataVerificationReport

# ... fetch bulletin ...

if bulletin_data:
    # Verify data quality
    verifier = DataVerificationReport()
    verification = verifier.verify_bulletin(bulletin_data, jtwc_data)

    # Alert if confidence is low
    if verification['confidence_score'] < 70:
        alert_message = f"""
⚠️ DATA QUALITY WARNING

Confidence Score: {verification['confidence_score']}%

Errors: {len(verification['errors'])}
Warnings: {len(verification['warnings'])}

Recommendation: {verification['recommendation'].upper()}

Please manually verify the data before trusting alerts.
        """
        notifier.send_message(alert_message)

        # Log for investigation
        logger.warning(f"Low confidence score: {verification}")
```

---

## Quick Implementation Checklist

**Phase 1: Immediate** (1-2 hours)
- [ ] Add `DataValidator.validate_bulletin()` to pagasa_parser.py
- [ ] Add coordinate range checks
- [ ] Add wind speed sanity checks
- [ ] Log validation warnings

**Phase 2: Short-term** (1 day)
- [ ] Create `validators/` package
- [ ] Implement all validator classes
- [ ] Add temporal consistency checks
- [ ] Create verification report tool

**Phase 3: Long-term** (1 week)
- [ ] Archive real bulletins for unit tests
- [ ] Create comprehensive test suite
- [ ] Add cross-validation with JTWC
- [ ] Implement automated verification in workflow

---

## Verification Workflow (Recommended)

```
1. Fetch bulletin from PAGASA
         ↓
2. Validate HTML (Layer 1)
         ↓
3. Parse bulletin
         ↓
4. Validate parsed data (Layer 2)
         ↓
5. Cross-validate with JTWC (Layer 3)
         ↓
6. Check temporal consistency (Layer 4)
         ↓
7. Generate confidence score
         ↓
8. If confidence < 70%: Alert admin for manual review
         ↓
9. If confidence >= 70%: Send alert to users
        ↓
10. Save verification report for audit trail
```

---

## Confidence Scoring System

| Score | Quality | Action |
|-------|---------|--------|
| 90-100% | Excellent | Send alert immediately |
| 70-89% | Good | Send alert with note |
| 50-69% | Fair | Send alert + warning to admin |
| <50% | Poor | Hold alert, notify admin for review |

---

## Summary

**Current state**: Minimal validation (only checks if coordinates exist)

**Recommended state**: 5-layer verification system with:
1. ✅ HTML validation
2. ✅ Data sanity checks
3. ✅ Cross-source validation
4. ✅ Temporal consistency
5. ✅ Unit tests with known data

**Next steps**:
1. Start with Phase 1 (sanity checks) - highest ROI
2. Add verification script to workflow
3. Archive real bulletins for testing
4. Gradually expand to all 5 layers

This ensures your bot sends accurate, reliable alerts while catching parsing errors before they reach users.
