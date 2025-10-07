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
        
        # System name and type
        if cyclone_name and cyclone_name.lower() not in ['unknown', 'none']:
            message += f"*System:* {cyclone_name}\n"
        else:
            message += f"*System:* {system_type}\n"
        
        message += f"*Type:* {system_type}\n"
        
        if is_outside_par:
            message += f"*Status:* Being monitored (Outside PAR)\n"
        else:
            message += f"*Status:* Active within Philippine Area of Responsibility\n"
        
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
        if eta and eta < 72:  # Only show ETA if within 72 hours
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
