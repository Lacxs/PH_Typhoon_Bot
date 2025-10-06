"""
Telegram Alert Notifier
Sends formatted typhoon and LPA alerts to Telegram
"""

import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send typhoon and LPA alerts via Telegram"""
    
    def __init__(self, token, chat_id):
        """
        Initialize Telegram notifier
        
        Args:
            token: Telegram bot token
            chat_id: Target chat/group ID
        """
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
    
    def send_alert(self, bulletin_data):
        """
        Send formatted weather alert
        
        Args:
            bulletin_data: Dict containing bulletin information
        """
        system_type = bulletin_data.get('type', 'Tropical Cyclone')
        
        if system_type == 'Low Pressure Area':
            message = self._format_lpa_message(bulletin_data)
        else:
            message = self._format_typhoon_message(bulletin_data)
        
        return self._send_message(message)
    
    def send_error_notification(self, error_message):
        """Send error notification to admin"""
        message = f"🚨 *Typhoon Bot Error*\n\n```\n{error_message}\n```"
        return self._send_message(message)
    
    def _format_lpa_message(self, data):
        """Format LPA alert message"""
        location = data.get('location', {})
        movement = data.get('movement', {})
        port_status = data.get('port_status', {})
        
        # Header with different emoji for LPA
        message = f"🌧️ *PAGASA Weather Update: Low Pressure Area*\n"
        message += f"_Monitoring potential tropical cyclone development_\n\n"
        
        # Location
        lat = location.get('latitude')
        lon = location.get('longitude')
        if lat and lon:
            message += f"📍 Location: {lat}°N, {lon}°E\n"
        
        # Movement (if available)
        direction = movement.get('direction')
        speed = movement.get('speed')
        if direction and speed:
            message += f"➡️ Movement: {direction} at {speed} km/h\n"
        elif direction:
            message += f"➡️ Movement: {direction}\n"
        else:
            message += f"➡️ Movement: Slow-moving or stationary\n"
        
        message += f"💨 Status: Low Pressure Area (pre-cyclone stage)\n"
        
        # Port status section
        message += "\n*🚢 Port Distances:*\n"
        
        # Sort ports by distance (closest first)
        sorted_ports = self._sort_ports_by_distance(port_status)
        
        for port_name in sorted_ports:
            status = port_status[port_name]
            message += self._format_port_distance(port_name, status)
        
        # Footer
        message += "\n⚠️ *Advisory:*\n"
        message += "LPAs may develop into tropical depressions. Monitor for updates.\n"
        message += "\n📊 Source: PAGASA (official)\n"
        
        # Timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        message += f"🕐 Updated: {timestamp} PHT"
        
        return message
    
    def _format_typhoon_message(self, data):
        """Format typhoon/tropical cyclone alert message"""
        cyclone_name = data.get('cyclone_name', 'Unknown')
        location = data.get('location', {})
        movement = data.get('movement', {})
        intensity = data.get('intensity', {})
        port_status = data.get('port_status', {})
        
        # Header
        message = f"⚠️ *PAGASA Typhoon Update: {cyclone_name}*\n"
        
        # Location
        lat = location.get('latitude')
        lon = location.get('longitude')
        if lat and lon:
            message += f"📍 Location: {lat}°N, {lon}°E\n"
        
        # Movement
        direction = movement.get('direction')
        speed = movement.get('speed')
        if direction and speed:
            message += f"➡️ Movement: {direction} at {speed} km/h\n"
        elif direction:
            message += f"➡️ Movement: {direction}\n"
        
        # Intensity
        winds = intensity.get('winds')
        gusts = intensity.get('gusts')
        if winds and gusts:
            message += f"💨 Intensity: {winds} km/h winds, {gusts} km/h gusts\n"
        elif winds:
            message += f"💨 Intensity: {winds} km/h winds\n"
        
        # Port status section
        message += "\n*🚢 Port Status:*\n"
        
        # Sort ports by threat level (TCWS > proximity > distance)
        sorted_ports = self._sort_ports_by_threat(port_status)
        
        for port_name in sorted_ports:
            status = port_status[port_name]
            message += self._format_port_status(port_name, status)
        
        # Footer
        next_bulletin = data.get('next_bulletin')
        if next_bulletin:
            message += f"\n⏰ Next bulletin: {next_bulletin} (Asia/Manila)\n"
        
        message += "\n📊 Sources: PAGASA (official)"
        if data.get('jtwc_available'):
            message += " | JTWC (forecast guidance)"
        
        # Timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        message += f"\n🕐 Updated: {timestamp} PHT"
        
        return message
    
    def _sort_ports_by_threat(self, port_status):
        """Sort ports by threat level (most threatened first)"""
        def threat_score(port_name):
            status = port_status[port_name]
            score = 0
            
            # TCWS level contributes most
            tcws = status.get('tcws')
            if tcws:
                score += tcws * 1000
            
            # Proximity
            if status.get('in_proximity'):
                score += 500
            
            # ETA (closer = higher score)
            eta = status.get('eta_hours')
            if eta:
                score += (100 - min(eta, 100))
            
            # Distance (closer = higher score)
            distance = status.get('distance_km', 999)
            score += (1000 - min(distance, 1000)) / 10
            
            return -score  # Negative for descending sort
        
        return sorted(port_status.keys(), key=threat_score)
    
    def _sort_ports_by_distance(self, port_status):
        """Sort ports by distance (closest first)"""
        def distance_score(port_name):
            status = port_status[port_name]
            return status.get('distance_km', 9999)
        
        return sorted(port_status.keys(), key=distance_score)
    
    def _format_port_status(self, port_name, status):
        """Format individual port status line (for typhoons)"""
        tcws = status.get('tcws')
        eta = status.get('eta_hours')
        distance = status.get('distance_km')
        in_proximity = status.get('in_proximity', False)
        
        # Icon based on threat level
        if tcws and tcws >= 3:
            icon = "🔴"
        elif tcws and tcws >= 1:
            icon = "🟡"
        elif in_proximity:
            icon = "🟠"
        else:
            icon = "🟢"
        
        line = f"{icon} *{port_name}*"
        
        # TCWS signal
        if tcws:
            line += f" – TCWS #{tcws}"
        else:
            line += " – No signal"
        
        # ETA
        if eta:
            if eta < 1:
                line += f" (~{int(eta * 60)} min ETA)"
            else:
                line += f" (~{int(eta)} h ETA)"
        
        # Distance if not under signal
        if not tcws and distance:
            line += f" ({int(distance)} km away)"
        
        line += "\n"
        
        return line
    
    def _format_port_distance(self, port_name, status):
        """Format port distance line (for LPAs)"""
        distance = status.get('distance_km')
        in_proximity = status.get('in_proximity', False)
        
        # Icon based on proximity
        if distance < 200:
            icon = "🟠"
        elif in_proximity:  # < 300 km
            icon = "🟡"
        else:
            icon = "🟢"
        
        line = f"{icon} *{port_name}* – {int(distance)} km away"
        
        if distance < 300:
            line += " (within monitoring range)"
        
        line += "\n"
        
        return line
    
    def _send_message(self, text):
        """
        Send message to Telegram
        
        Args:
            text: Message text (Markdown formatted)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            url = f"{self.base_url}/sendMessage"
            
            payload = {
                'chat_id': self.chat_id,
                'text': text,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': True
            }
            
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('ok'):
                logger.info("Telegram message sent successfully")
                return True
            else:
                logger.error(f"Telegram API error: {result}")
                return False
        
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    def send_test_message(self):
        """Send a test message to verify bot configuration"""
        message = "✅ *Typhoon Monitor Bot*\n\nBot is configured and running!\n\n🔔 You will receive typhoon and LPA alerts here."
        return self._send_message(message)
    
    def send_status_update(self):
        """Send daily status update when no threats exist"""
        now = datetime.now()
        date_str = now.strftime("%B %d, %Y")
        time_str = now.strftime("%I:%M %p")
        
        message = f"☀️ *Daily Weather Status*\n"
        message += f"_{date_str}_\n\n"
        message += "✅ No tropical cyclones or low pressure areas detected within monitoring range.\n\n"
        message += "🔍 Bot is actively monitoring PAGASA updates.\n"
        message += f"🕐 Status as of {time_str} PHT"
        
        return self._send_message(message)
