"""
Philippine Typhoon Monitoring Bot
Main orchestrator for PAGASA + JTWC bulletin tracking
"""

import os
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fetchers.pagasa_parser import PAGASAParser
from fetchers.jtwc_parser import JTWCParser
from processors.compute_eta import PortETACalculator
from notifiers.telegram_alert import TelegramNotifier

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Philippine timezone (UTC+8)
PHT = timezone(timedelta(hours=8))

# Port coordinates (latitude, longitude) - Ordered North to South
PORTS = {
    "SBITC": (14.8045, 120.2663),     # Subic Bay International Terminal
    "MICT": (14.6036, 120.9466),      # Manila International Container Terminal
    "Bauan": (13.7823, 120.9895),     # Bauan International Port, Batangas
    "VCT": (10.7064, 122.5947),       # Visayas Container Terminal, Iloilo
    "MICTSI": (8.5533, 124.7667)      # Mindanao International Container Terminal
}

CACHE_FILE = Path("data/last_bulletin.json")
ARCHIVE_FILE = Path("data/bulletin_archive.json")
STATUS_FILE = Path("data/last_status_update.json")


def load_cache():
    """Load the last processed bulletin timestamp"""
    if CACHE_FILE.exists():
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_cache(data):
    """Save bulletin data to cache"""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def archive_bulletin(bulletin_data):
    """Archive bulletin for historical tracking"""
    ARCHIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    archive = []
    if ARCHIVE_FILE.exists():
        with open(ARCHIVE_FILE, 'r') as f:
            archive = json.load(f)
    
    archive.append({
        "timestamp": datetime.now(PHT).isoformat(),
        "data": bulletin_data
    })
    
    # Keep last 100 bulletins
    archive = archive[-100:]
    
    with open(ARCHIVE_FILE, 'w') as f:
        json.dump(archive, f, indent=2)


def should_send_alert(current_bulletin, cached_bulletin):
    """Determine if we should send a new alert"""
    if not cached_bulletin:
        return True
    
    # Check if bulletin timestamp changed
    if current_bulletin.get("bulletin_time") != cached_bulletin.get("bulletin_time"):
        return True
    
    # Check if any port status changed significantly
    current_ports = current_bulletin.get("port_status", {})
    cached_ports = cached_bulletin.get("port_status", {})
    
    for port in PORTS.keys():
        current = current_ports.get(port, {})
        cached = cached_ports.get(port, {})
        
        # TCWS level changed
        if current.get("tcws") != cached.get("tcws"):
            return True
        
        # ETA changed by more than 3 hours
        current_eta = current.get("eta_hours")
        cached_eta = cached.get("eta_hours")
        if current_eta and cached_eta:
            if abs(current_eta - cached_eta) > 3:
                return True
    
    return False


def should_send_status_update():
    """Check if we should send status update (twice daily at 7 AM and 7 PM PHT)"""
    if not STATUS_FILE.exists():
        return True
    
    try:
        with open(STATUS_FILE, 'r') as f:
            last_status = json.load(f)
        
        last_update_str = last_status.get('last_update')
        if not last_update_str:
            return True
        
        last_update = datetime.fromisoformat(last_update_str)
        now = datetime.now(PHT)
        
        # Send update if more than 12 hours since last update
        hours_since = (now - last_update).total_seconds() / 3600
        if hours_since >= 12:
            return True
        
        # Check if we should send morning report (7 AM)
        if now.hour >= 7 and now.hour < 19:
            # Morning window (7 AM - 7 PM)
            if last_update.date() < now.date() or last_update.hour < 7:
                return True
        
        # Check if we should send evening report (7 PM)
        if now.hour >= 19:
            # Evening window (7 PM - midnight)
            if last_update.hour < 19 or last_update.date() < now.date():
                return True
        
        return False
    
    except Exception as e:
        logger.warning(f"Error checking status update time: {e}")
        return True


def save_status_update():
    """Save the timestamp of the last status update"""
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATUS_FILE, 'w') as f:
        json.dump({
            'last_update': datetime.now(PHT).isoformat()
        }, f, indent=2)


def main():
    """Main execution flow"""
    logger.info("Starting Typhoon Monitor Bot...")
    
    # Check if manual status report was requested
    force_status = os.getenv("FORCE_STATUS_REPORT", "false").lower() == "true"
    
    # Initialize components
    pagasa = PAGASAParser()
    jtwc = JTWCParser()
    calculator = PortETACalculator(PORTS)
    notifier = TelegramNotifier(
        token=os.getenv("TELEGRAM_TOKEN"),
        chat_id=os.getenv("TELEGRAM_CHAT_ID")
    )
    
    try:
        # Fetch PAGASA data
        logger.info("Fetching PAGASA bulletin...")
        pagasa_data = pagasa.fetch_latest_bulletin()
        
        if not pagasa_data:
            logger.warning("No active typhoon bulletin from PAGASA")
            
            # Send status update if scheduled OR manually forced
            if should_send_status_update() or force_status:
                logger.info("Sending status update...")
                if force_status:
                    logger.info("Status report manually triggered")
                notifier.send_status_update()
                save_status_update()
            
            return
        
        logger.info(f"Found active cyclone: {pagasa_data.get('name', 'Unknown')}")
        
        # Fetch JTWC data (optional, for forecast guidance)
        jtwc_data = None
        try:
            logger.info("Fetching JTWC forecast guidance...")
            jtwc_data = jtwc.fetch_latest_forecast(pagasa_data.get('name'))
        except Exception as e:
            logger.warning(f"JTWC fetch failed (non-critical): {e}")
        
        # Calculate port status
        logger.info("Calculating port distances and ETAs...")
        port_status = calculator.calculate_all_ports(
            lat=pagasa_data['latitude'],
            lon=pagasa_data['longitude'],
            movement_dir=pagasa_data.get('movement_direction'),
            movement_speed=pagasa_data.get('movement_speed'),
            tcws_data=pagasa_data.get('tcws_areas', {})
        )
        
        # Build complete bulletin data
        bulletin_data = {
            "bulletin_time": pagasa_data.get('bulletin_time'),
            "cyclone_name": pagasa_data.get('name'),
            "type": pagasa_data.get('type', 'Tropical Cyclone'),
            "location": {
                "latitude": pagasa_data['latitude'],
                "longitude": pagasa_data['longitude']
            },
            "movement": {
                "direction": pagasa_data.get('movement_direction'),
                "speed": pagasa_data.get('movement_speed')
            },
            "intensity": {
                "winds": pagasa_data.get('max_winds'),
                "gusts": pagasa_data.get('max_gusts')
            },
            "port_status": port_status,
            "next_bulletin": pagasa_data.get('next_bulletin'),
            "jtwc_available": jtwc_data is not None
        }
        
        # Check if we should send alert
        cached = load_cache()
        
        if should_send_alert(bulletin_data, cached):
            logger.info("Sending Telegram alert...")
            notifier.send_alert(bulletin_data)
            
            # Save to cache and archive
            save_cache(bulletin_data)
            archive_bulletin(bulletin_data)
            
            logger.info("Alert sent successfully")
        else:
            logger.info("No significant changes detected, skipping alert")
    
    except Exception as e:
        logger.error(f"Error in main execution: {e}", exc_info=True)
        # Send error notification
        try:
            notifier.send_error_notification(str(e))
        except:
            pass
        raise


if __name__ == "__main__":
    main()
