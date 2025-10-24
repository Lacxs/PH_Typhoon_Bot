"""
Quick test script for validators
"""

from validators.data_validator import DataValidator
from validators.temporal_validator import TemporalValidator

print("="*80)
print("VALIDATOR TESTING")
print("="*80)

# Test 1: Valid bulletin data
print("\n[TEST 1] Valid Bulletin Data")
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

if is_valid:
    print("✅ PASSED - Valid bulletin accepted")
else:
    print(f"❌ FAILED - {errors}")

if warnings:
    print(f"⚠️  Warnings: {warnings}")

# Test 2: Invalid coordinates (outside monitoring zone)
print("\n[TEST 2] Invalid Coordinates (Outside Monitoring Zone)")
print("-"*80)

invalid_coords = {
    'name': 'Test',
    'type': 'Typhoon',
    'latitude': 50.0,  # Too far north
    'longitude': 200.0,  # Invalid longitude
    'max_winds': 120,
    'max_gusts': 150,
    'movement_direction': 'NORTH',
    'movement_speed': 15,
    'bulletin_time': 'Test',
    'tcws_areas': {}
}

is_valid, errors, warnings = DataValidator.validate_bulletin(invalid_coords)

if not is_valid:
    print("✅ PASSED - Invalid coordinates rejected")
    print(f"   Errors: {errors}")
else:
    print("❌ FAILED - Should have rejected invalid coordinates")

# Test 3: Unrealistic wind speeds
print("\n[TEST 3] Unrealistic Wind Speed")
print("-"*80)

unrealistic_winds = {
    'name': 'Test',
    'type': 'Typhoon',
    'latitude': 14.8,
    'longitude': 121.2,
    'max_winds': 500,  # Impossible
    'max_gusts': 600,
    'movement_direction': 'WEST',
    'movement_speed': 20,
    'bulletin_time': 'Test',
    'tcws_areas': {}
}

is_valid, errors, warnings = DataValidator.validate_bulletin(unrealistic_winds)

if not is_valid:
    print("✅ PASSED - Unrealistic winds rejected")
    print(f"   Errors: {errors}")
else:
    print("❌ FAILED - Should have rejected unrealistic wind speeds")

# Test 4: Gusts < Winds (physics violation)
print("\n[TEST 4] Gusts Lower Than Sustained Winds (Physics Violation)")
print("-"*80)

physics_violation = {
    'name': 'Test',
    'type': 'Typhoon',
    'latitude': 14.8,
    'longitude': 121.2,
    'max_winds': 120,
    'max_gusts': 100,  # Should be higher than winds
    'movement_direction': 'WEST',
    'movement_speed': 20,
    'bulletin_time': 'Test',
    'tcws_areas': {}
}

is_valid, errors, warnings = DataValidator.validate_bulletin(physics_violation)

if not is_valid:
    print("✅ PASSED - Physics violation detected")
    print(f"   Errors: {errors}")
else:
    print("❌ FAILED - Should have detected gusts < winds")

# Test 5: Temporal validation - realistic movement
print("\n[TEST 5] Temporal Validation - Realistic Movement")
print("-"*80)

prev_bulletin = {
    'latitude': 14.0,
    'longitude': 120.0,
    'max_winds': 100
}

curr_bulletin = {
    'latitude': 14.5,  # Moved ~55km north
    'longitude': 120.5,  # Moved ~55km east
    'max_winds': 110
}

time_diff = 3.0  # 3 hours

is_realistic, temp_warnings = TemporalValidator.validate_position_change(
    prev_bulletin, curr_bulletin, time_diff
)

if is_realistic:
    print("✅ PASSED - Realistic movement accepted")
    print(f"   Distance: ~80km in 3 hours (~27 km/h)")
else:
    print(f"❌ FAILED - {temp_warnings}")

# Test 6: Temporal validation - unrealistic teleportation
print("\n[TEST 6] Temporal Validation - Unrealistic Teleportation")
print("-"*80)

curr_bulletin_teleport = {
    'latitude': 20.0,  # Jumped ~665km north
    'longitude': 125.0,  # Jumped ~555km east
    'max_winds': 110
}

is_realistic, temp_warnings = TemporalValidator.validate_position_change(
    prev_bulletin, curr_bulletin_teleport, 1.0  # 1 hour
)

if not is_realistic:
    print("✅ PASSED - Teleportation detected")
    print(f"   Warnings: {temp_warnings}")
else:
    print("❌ FAILED - Should have detected unrealistic movement")

# Test 7: Validate direction
print("\n[TEST 7] Direction Validation")
print("-"*80)

is_valid, msg = DataValidator.validate_direction("NORTHWEST")
print(f"NORTHWEST: {'✅ Valid' if is_valid else f'❌ Invalid - {msg}'}")

is_valid, msg = DataValidator.validate_direction("NW")
print(f"NW: {'✅ Valid' if is_valid else f'❌ Invalid - {msg}'}")

is_valid, msg = DataValidator.validate_direction("NORTHWESTWARD")
print(f"NORTHWESTWARD: {'✅ Valid' if is_valid else f'❌ Invalid - {msg}'}")

is_valid, msg = DataValidator.validate_direction("INVALID_DIR")
print(f"INVALID_DIR: {'❌ Invalid (expected)' if not is_valid else '✅ Valid'}")

print("\n" + "="*80)
print("VALIDATION TESTS COMPLETE")
print("="*80)
