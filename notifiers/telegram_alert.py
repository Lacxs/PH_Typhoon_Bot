"""
Telegram Alert Notifier
Sends formatted typhoon and LPA alerts to Telegram
"""

import logging
import requests
import io
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# Philippine timezone (UTC+8)
PHT = timezone(timedelta(hours=8))


def create_storm_map(bulletin_data):
    """
    Create a simple storm track map showing typhoon position and terminals
    Returns image bytes for Telegram
    """
    try:
        import matplotlib
        matplotlib.use('Agg')  # Non-interactive backend
        import matplotlib.pyplot as plt
        from matplotlib.patches import Circle
        import numpy as np
        
        location = bulletin_data.get('location', {})
        storm_lat = location.get('latitude')
        storm_lon = location.get('longitude')
        
        if not storm_lat or not storm_lon:
            return None
        
        # Port coordinates
        ports = {
            "SBITC": (14.8045, 120.2663),
            "MICT": (14.6036, 120.9466),
            "Bauan": (13.7823, 120.9895),
            "VCT": (10.7064, 122.5947),
            "MICTSI": (8.5533, 124.7667)
        }
        
        # Create figure
        fig, ax = plt.subplots(figsize=(10, 8))
        
        # Plot Philippines outline (simplified box)
        phil_lat = [5, 5, 21, 21, 5]
        phil_lon = [116, 127, 127, 116, 116]
        ax.plot(phil_lon, phil_lat, 'k-', linewidth=2, alpha=0.3)
        
        # Plot 700km monitoring circle
        circle = Circle((storm_lon, storm_lat), 700/111, fill=False, 
                       edgecolor='orange', linestyle='--', linewidth=2, alpha=0.5)
        ax.add_patch(circle)
        
        # Plot storm position
        ax.plot(storm_lon, storm_lat, 'r*', markersize=30, 
               label=f"{bulletin_data.get('cyclone_name', 'Storm')}")
        
        # Plot terminals
        port_status = bulletin_data.get('port_status', {})
        for port_name, (lat, lon) in ports.items():
            status = port_status.get(port_name, {})
            tcws = status.get('tcws')
            
            # Color based on threat level
            if tcws and tcws >= 3:
                color = 'red'
                marker = 's'
                size = 200
            elif tcws and tcws >= 1:
                color = 'orange'
                marker = 's'
                size = 150
            elif status.get('in_proximity'):
                color = 'yellow'
                marker = 'o'
                size = 100
            else:
                color = 'green'
                marker = 'o'
                size = 80
            
            ax.scatter(lon, lat, c=color, marker=marker, s=size, 
                      edgecolors='black', linewidths=1.5, zorder=5)
            ax.text(lon, lat-0.3, port_name, ha='center', fontsize=9, 
                   fontweight='bold')
        
        # Labels and title
        cyclone_name = bulletin_data.get('cyclone_name', 'Storm')
        ax.set_title(f'Typhoon {cyclone_name} - ICTSI Terminal Monitoring', 
                    fontsize=14, fontweight='bold')
        ax.set_xlabel('Longitude', fontsize=11)
        ax.set_ylabel('Latitude', fontsize=11)
        ax.grid(True, alpha=0.3)
        ax.legend(loc='upper right')
        
        # Set bounds to show relevant area
        all_lons = [lon for _, (_, lon) in ports.items()] + [storm_lon]
        all_lats = [lat for _, (lat, _) in ports.items()] + [storm_lat]
        
        lon_margin = 2
        lat_margin = 2
        ax.set_xlim(min(all_lons) - lon_margin, max(all_lons) + lon_margin)
        ax.set_ylim(min(all_lats) - lat_margin, max(all_lats) + lat_margin)
        
        # Save to bytes
        buf = io.BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return buf.getvalue()
    
    except Exception as e:
        logger.error(f"Failed to create storm map: {e}")
        return None


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
        Send formatted weather alert (text only, map disabled)
        
        Args:
            bulletin_data: Dict containing bulletin information
        """
        system_type = bulletin_data.get('type', 'Tropical Cyclone')
        
        if system_type == 'Low Pressure Area':
            message = self._format_lpa_message(bulletin_data)
        else:
            message = self._format_typhoon_message(bulletin_data)
        
        # Send text-only message (map disabled)
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
        """Format typhoon/tropical cyclone alert message - Professional Option B style"""
        cyclone_name = data.get('cyclone_name', 'Unknown')
        system_type = data.get('type', 'Tropical Cyclone')
        location = data.get('location', {})
        movement = data.get('movement', {})
        intensity = data.get('intensity', {})
        port_status = data.get('port_status', {})
        
        # Determine if system is outside PAR
        is_outside_par = 'outside' in system_type.lower() or 'outside' in cyclone_name.lower()
        
        # Choose appropriate emoji and header
        if 'super typhoon' in system_type.lower():
            emoji = '🌪️'
        elif 'typhoon' in system_type.lower():
            emoji = '🌀'
        elif 'tropical storm' in system_type.lower():
            emoji = '🌊'
        else:
            emoji = '🌧️'
        
        # === HEADER ===
        message = f"{emoji} *PAGASA WEATHER BULLETIN*\n\n"
        
        # System name and classification
        if cyclone_name and cyclone_name.lower() not in ['unknown', 'none', 'tropical depression', 'tropical storm']:
            # Has a proper name (like "Paolo")
            message += f"*Name:* {cyclone_name}\n"
            message += f"*Classification:* {system_type}\n"
        else:
            # No proper name, just show classification
            message += f"*System:* {system_type}\n"
        
        # Status line
        if is_outside_par:
            message += f"*Location:* Outside Philippine Area of Responsibility\n"
            message += f"*Status:* Being monitored\n"
        else:
            message += f"*Location:* Within Philippine Area of Responsibility\n"
            message += f"*Status:* Active\n"
        
        # === CURRENT DATA SECTION ===
        message += f"\n📊 *CURRENT DATA*\n"
        message += f"━━━━━━━━━━━━━━━━━━━━\n"
        
        # Position
        lat = location.get('latitude')
        lon = location.get('longitude')
        if lat and lon:
            lat_dir = 'N' if lat >= 0 else 'S'
            lon_dir = 'E' if lon >= 0 else 'W'
            message += f"*Position:* {abs(lat):.1f}°{lat_dir}, {abs(lon):.1f}°{lon_dir}\n"
            
            # Calculate distance from Manila for context
            manila_lat, manila_lon = 14.6036, 120.9466
            from math import radians, cos, sin, asin, sqrt
            
            # Haversine formula
            lat1, lon1, lat2, lon2 = map(radians, [manila_lat, manila_lon, lat, lon])
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * asin(sqrt(a))
            distance_km = 6371 * c
            
            # Determine direction from Manila
            if lon > 125:
                direction = "East"
            elif lon < 118:
                direction = "West"
            else:
                if lat > 14.6:
                    direction = "North"
                else:
                    direction = "South"
            
            if lat > 15:
                region = "Luzon"
            elif lat > 10:
                region = "Visayas"
            else:
                region = "Mindanao"
            
            message += f"*Distance:* {int(distance_km)} km {direction} of {region}\n"
        
        # Intensity
        winds = intensity.get('winds')
        gusts = intensity.get('gusts')
        if winds and gusts:
            message += f"*Winds:* {winds} km/h (Gusts: {gusts} km/h)\n"
        elif winds:
            message += f"*Winds:* {winds} km/h\n"
        
        # Movement
        direction = movement.get('direction')
        speed = movement.get('speed')
        if direction and speed:
            # Format direction nicely
            dir_formatted = direction.replace('WARD', '').title()
            message += f"*Moving:* {dir_formatted} at {speed} km/h\n"
        elif direction:
            message += f"*Moving:* {direction.title()}\n"
        else:
            message += f"*Moving:* Slow-moving or quasi-stationary\n"
        
        # === TERMINAL STATUS SECTION ===
        message += f"\n🏗️ *TERMINAL STATUS*\n"
        message += f"━━━━━━━━━━━━━━━━━━━━\n"
        
        # Sort ports by threat level (most threatened first)
        sorted_ports = self._sort_ports_by_threat(port_status)
        
        for port_name in sorted_ports:
            status = port_status[port_name]
            message += self._format_port_status_professional(port_name, status)
        
        # === ACTION RECOMMENDATIONS ===
        recommendations = self._get_action_recommendations(port_status)
        if recommendations:
            message += f"\n⚠️ *RECOMMENDED ACTIONS*\n"
            message += f"━━━━━━━━━━━━━━━━━━━━\n"
            message += f"{recommendations}\n"
        
        # === FOOTER ===
        # Next bulletin time
        next_bulletin = data.get('next_bulletin')
        if next_bulletin:
            message += f"\n⏰ *Next Bulletin:* {next_bulletin}\n"
        
        # Timestamp
        timestamp = datetime.now(PHT).strftime("%Y-%m-%d %H:%M PHT")
        message += f"\n*Updated:* {timestamp}"
        
        return message
    
    def _format_port_status_professional(self, port_name, status):
        """Format individual port status line - Professional style for Option B"""
        tcws = status.get('tcws')
        eta = status.get('eta_hours')
        distance = status.get('distance_km')
        in_proximity = status.get('in_proximity', False)
        
        # Determine status icon and text
        if tcws and tcws >= 3:
            icon = "🔴"
            status_text = f"Signal #{tcws}"
        elif tcws and tcws >= 1:
            icon = "🟡"
            status_text = f"Signal #{tcws}"
        elif in_proximity:
            icon = "🟠"
            status_text = "Monitoring"
        else:
            icon = "✅"
            status_text = "Clear"
        
        # Build the line
        line = f"{icon} *{port_name}* - {status_text}"
        
        # Add distance in parentheses
        if distance:
            line += f" ({int(distance)} km)"
        
        # Add ETA if relevant
        if eta and eta < 72:
            if eta < 1:
                line += f" • ETA: ~{int(eta * 60)} min"
            elif eta < 24:
                line += f" • ETA: ~{int(eta)}h"
            else:
                days = int(eta / 24)
                hours = int(eta % 24)
                if hours > 0:
                    line += f" • ETA: ~{days}d {hours}h"
                else:
                    line += f" • ETA: ~{days}d"
        
        line += "\n"
        
        return line
    
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
    
    def _get_action_recommendations(self, port_status):
        """Generate action recommendations based on TCWS levels"""
        # Find highest TCWS level
        max_tcws = 0
        affected_ports = []
        
        for port_name, status in port_status.items():
            tcws = status.get('tcws')
            if tcws:
                if tcws > max_tcws:
                    max_tcws = tcws
                    affected_ports = [port_name]
                elif tcws == max_tcws:
                    affected_ports.append(port_name)
        
        if max_tcws == 0:
            return None
        
        recommendations = {
            1: "• Monitor weather updates closely\n• Prepare to secure loose equipment\n• Review emergency procedures\n• Maintain normal operations with caution",
            2: "• Secure all containers and equipment\n• Restrict non-essential operations\n• Prepare evacuation plans\n• Stock emergency supplies\n• Brief all personnel on storm procedures",
            3: "• CEASE OPERATIONS IMMEDIATELY\n• Evacuate non-essential personnel\n• Secure all assets and facilities\n• Activate emergency response team\n• Monitor communications continuously",
            4: "• FULL EVACUATION - CRITICAL THREAT\n• All personnel to safe locations\n• Complete operational shutdown\n• Activate disaster response protocols\n• Prepare for significant damage assessment",
            5: "• EXTREME DANGER - CATASTROPHIC CONDITIONS\n• Complete evacuation mandatory\n• Take shelter in reinforced structures\n• Expect widespread severe damage\n• Emergency services may be unavailable"
        }
        
        ports_str = ", ".join(affected_ports)
        return f"*TCWS #{max_tcws}* at {ports_str}:\n{recommendations.get(max_tcws, '')}"
    
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
    
    def _send_photo(self, photo_bytes, caption):
        """
        Send photo with caption to Telegram
        
        Args:
            photo_bytes: Image bytes
            caption: Photo caption (Markdown formatted)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            url = f"{self.base_url}/sendPhoto"
            
            files = {
                'photo': ('storm_map.png', photo_bytes, 'image/png')
            }
            
            data = {
                'chat_id': self.chat_id,
                'caption': caption,
                'parse_mode': 'Markdown'
            }
            
            response = requests.post(url, files=files, data=data, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('ok'):
                logger.info("Telegram photo sent successfully")
                return True
            else:
                logger.error(f"Telegram API error: {result}")
                return False
        
        except Exception as e:
            logger.error(f"Failed to send Telegram photo: {e}")
            # Fallback to text-only message
            return self._send_message(caption)
    
    def send_test_message(self):
        """Send a test message to verify bot configuration"""
        message = "✅ *Typhoon Monitor Bot*\n\nBot is configured and running!\n\n🔔 You will receive typhoon and LPA alerts here."
        return self._send_message(message)
    
    def send_status_update(self, forecast_data=None):
        """Send twice-daily status update when no threats exist"""
        now = datetime.now(PHT)
        date_str = now.strftime("%B %d, %Y")
        time_str = now.strftime("%I:%M %p")
        
        # Determine if morning or evening report
        if now.hour < 12:
            report_type = "Morning Weather Report"
            report_emoji = "🌅"
        else:
            report_type = "Evening Weather Report"
            report_emoji = "🌆"
        
        message = f"{report_emoji} *{report_type}*\n"
        message += f"_{date_str}_\n\n"
        message += "✅ No tropical cyclones or low pressure areas detected within 700 km monitoring range.\n\n"
        
        # Add 5-day outlook if available
        if forecast_data and forecast_data.get('summary'):
            message += "📊 *5-Day Outlook:*\n"
            
            summary = forecast_data.get('summary')
            message += f"• {summary}\n"
            
            # Add detailed area info if available
            areas = forecast_data.get('areas', [])
            if areas:
                for area in areas[:2]:  # Limit to 2 areas
                    location = area.get('location', 'Unknown')
                    probability = area.get('probability', 'UNKNOWN')
                    timeframe = area.get('timeframe', '3-5 days')
                    
                    # Only show if not already in summary
                    if location.lower() not in summary.lower():
                        message += f"• Area: {location}\n"
                        message += f"• Formation probability: {probability}\n"
                        message += f"• Timeframe: {timeframe}\n"
            
            message += "\n"
        
        message += "🔍 Bot is actively monitoring PAGASA updates.\n"
        message += f"🕐 Report as of {time_str} PHT"
        
        return self._send_message(message)
