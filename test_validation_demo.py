"""
Validation System Demo
Shows how the validation system catches bad data
"""

import logging
from validators.data_validator import DataValidator
from validators.temporal_validator import TemporalValidator

# Setup logging to see what the validators output
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

print("="*80)
print("VALIDATION SYSTEM DEMONSTRATION")
print("="*80)

# ============================================================
# DEMO 1: Valid Typhoon Data (Should Pass)
# ============================================================
print("\n[DEMO 1] Valid Typhoon Data - Tropical Storm Kristine")
print("-"*80)

valid_bulletin = {
    'name': 'Kristine',
    'type': 'Tropical Storm',
    'latitude': 14.8,
    'longitude': 121.2,
    'max_winds': 85,
    'max_gusts': 105,
    'movement_direction': 'WEST',
    'movement_speed': 20,
    'bulletin_time': '10:00 AM, 24 October 2024',
    'tcws_areas': {1: ['Manila', 'Quezon'], 2: ['Batangas']}
}

is_valid, errors, warnings = DataValidator.validate_bulletin(valid_bulletin)

print(f"Bulletin: {valid_bulletin['name']} ({valid_bulletin['type']})")
print(f"Location: {valid_bulletin['latitude']}°N, {valid_bulletin['longitude']}°E")
print(f"Winds: {valid_bulletin['max_winds']} km/h, Gusts: {valid_bulletin['max_gusts']} km/h")
print(f"Movement: {valid_bulletin['movement_direction']} at {valid_bulletin['movement_speed']} km/h")
print()

if is_valid:
    print("✅ VALIDATION PASSED - Alert would be sent to users")
else:
    print(f"❌ VALIDATION FAILED - Alert blocked")
    for error in errors:
        print(f"   Error: {error}")

if warnings:
    print("Warnings:")
    for warning in warnings:
        print(f"   ⚠️  {warning}")

# ============================================================
# DEMO 2: Invalid Coordinates (Should Fail)
# ============================================================
print("\n[DEMO 2] Invalid Coordinates - Parsing Error Simulation")
print("-"*80)

invalid_coords = {
    'name': 'Bad Data',
    'type': 'Typhoon',
    'latitude': 50.0,      # Too far north - not in Philippine area
    'longitude': 200.0,    # Invalid longitude
    'max_winds': 120,
    'max_gusts': 150,
    'movement_direction': 'NORTH',
    'movement_speed': 15,
    'bulletin_time': 'Test',
    'tcws_areas': {}
}

is_valid, errors, warnings = DataValidator.validate_bulletin(invalid_coords)

print(f"Bulletin: {invalid_coords['name']}")
print(f"Location: {invalid_coords['latitude']}°N, {invalid_coords['longitude']}°E")
print()

if is_valid:
    print("✅ VALIDATION PASSED")
else:
    print("❌ VALIDATION FAILED - Alert blocked (correct!)")
    print("\nErrors detected:")
    for error in errors:
        print(f"   • {error}")
    print("\n📁 In production, this data would be saved to: data/failed_validation.json")
    print("📧 Admin would receive error notification")

# ============================================================
# DEMO 3: Unrealistic Wind Speeds (Should Fail)
# ============================================================
print("\n[DEMO 3] Unrealistic Wind Speeds - Parser Bug Simulation")
print("-"*80)

unrealistic_winds = {
    'name': 'Super Bug',
    'type': 'Typhoon',
    'latitude': 14.8,
    'longitude': 121.2,
    'max_winds': 500,     # Impossible - max ever recorded is 305 km/h
    'max_gusts': 600,
    'movement_direction': 'WEST',
    'movement_speed': 20,
    'bulletin_time': 'Test',
    'tcws_areas': {}
}

is_valid, errors, warnings = DataValidator.validate_bulletin(unrealistic_winds)

print(f"Bulletin: {unrealistic_winds['name']}")
print(f"Winds: {unrealistic_winds['max_winds']} km/h, Gusts: {unrealistic_winds['max_gusts']} km/h")
print()

if is_valid:
    print("✅ VALIDATION PASSED")
else:
    print("❌ VALIDATION FAILED - Alert blocked (correct!)")
    print("\nErrors detected:")
    for error in errors:
        print(f"   • {error}")

# ============================================================
# DEMO 4: Physics Violation - Gusts < Winds (Should Fail)
# ============================================================
print("\n[DEMO 4] Physics Violation - Gusts Lower Than Sustained Winds")
print("-"*80)

physics_error = {
    'name': 'Physics Bug',
    'type': 'Typhoon',
    'latitude': 14.8,
    'longitude': 121.2,
    'max_winds': 120,
    'max_gusts': 100,     # Should be higher than sustained winds!
    'movement_direction': 'WEST',
    'movement_speed': 20,
    'bulletin_time': 'Test',
    'tcws_areas': {}
}

is_valid, errors, warnings = DataValidator.validate_bulletin(physics_error)

print(f"Bulletin: {physics_error['name']}")
print(f"Winds: {physics_error['max_winds']} km/h, Gusts: {physics_error['max_gusts']} km/h")
print("(Gusts should ALWAYS be higher than sustained winds)")
print()

if is_valid:
    print("✅ VALIDATION PASSED")
else:
    print("❌ VALIDATION FAILED - Alert blocked (correct!)")
    print("\nErrors detected:")
    for error in errors:
        print(f"   • {error}")

# ============================================================
# DEMO 5: Temporal Validation - Realistic Movement (Should Pass)
# ============================================================
print("\n[DEMO 5] Temporal Validation - Realistic Typhoon Movement")
print("-"*80)

prev_bulletin = {
    'name': 'Kristine',
    'latitude': 14.0,
    'longitude': 120.0,
    'max_winds': 100
}

curr_bulletin_realistic = {
    'name': 'Kristine',
    'latitude': 14.5,  # Moved ~55km north
    'longitude': 120.5,  # Moved ~55km east
    'max_winds': 110
}

time_diff = 3.0  # 3 hours between bulletins

print(f"Previous: {prev_bulletin['latitude']}°N, {prev_bulletin['longitude']}°E")
print(f"Current:  {curr_bulletin_realistic['latitude']}°N, {curr_bulletin_realistic['longitude']}°E")
print(f"Time:     {time_diff} hours")
print()

is_realistic, temp_warnings = TemporalValidator.validate_position_change(
    prev_bulletin, curr_bulletin_realistic, time_diff
)

if is_realistic:
    print("✅ TEMPORAL VALIDATION PASSED - Movement is realistic (~27 km/h)")
    print("   Alert would be sent to users")
else:
    print("❌ TEMPORAL VALIDATION FAILED")
    for warning in temp_warnings:
        print(f"   • {warning}")

# ============================================================
# DEMO 6: Temporal Validation - Unrealistic Jump (Should Fail)
# ============================================================
print("\n[DEMO 6] Temporal Validation - Typhoon 'Teleportation'")
print("-"*80)

curr_bulletin_teleport = {
    'name': 'Kristine',
    'latitude': 20.0,  # Jumped ~665km north!
    'longitude': 125.0,  # Jumped ~555km east!
    'max_winds': 110
}

print(f"Previous: {prev_bulletin['latitude']}°N, {prev_bulletin['longitude']}°E at 07:00 AM")
print(f"Current:  {curr_bulletin_teleport['latitude']}°N, {curr_bulletin_teleport['longitude']}°E at 08:00 AM")
print(f"Time:     1 hour (impossible to move this far!)")
print()

is_realistic, temp_warnings = TemporalValidator.validate_position_change(
    prev_bulletin, curr_bulletin_teleport, 1.0
)

if is_realistic:
    print("✅ TEMPORAL VALIDATION PASSED")
else:
    print("❌ TEMPORAL VALIDATION FAILED - Alert blocked (correct!)")
    print("\nDetected issues:")
    for warning in temp_warnings:
        print(f"   • {warning}")
    print("\n📧 Admin would receive error notification:")
    print("   '⚠️ VALIDATION ERROR - Temporal validation failed'")

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "="*80)
print("VALIDATION SYSTEM SUMMARY")
print("="*80)
print("""
What the validation system protects against:

✅ Invalid coordinates (outside Philippine area)
✅ Unrealistic wind speeds (>350 km/h)
✅ Physics violations (gusts < winds)
✅ Impossible movement (typhoon teleportation)
✅ Unrealistic movement speeds (>100 km/h)
✅ Invalid direction strings
✅ Invalid TCWS levels

When validation fails:
1. ❌ Alert is blocked (no false information sent)
2. 💾 Failed data saved to data/failed_validation.json
3. 📧 Admin receives error notification
4. 📝 Full error details logged for debugging

When validation passes:
1. ✅ Alert sent to users as normal
2. ⚠️  Warnings logged for review (if any)
3. 📊 Data archived for historical tracking
""")

print("="*80)
print("DEMONSTRATION COMPLETE")
print("="*80)
