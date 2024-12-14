import logging
import time
import threading
import serial.tools.list_ports
import re
from typing import Dict, Optional, List
from config import config

logger = logging.getLogger(__name__)

class ModemManager:
    def __init__(self, server=None):
        self.modems: Dict[str, Dict] = {}  # port -> modem_info
        self.running = False
        self.scan_thread = None
        self.server = server  # Add server reference
        self.connected_modems = set()  # Track connected modems

    def start(self):
        """Start modem scanning."""
        self.running = True
        self.scan_thread = threading.Thread(target=self._scan_loop, daemon=True)
        self.scan_thread.start()

    def stop(self):
        """Stop modem scanning."""
        self.running = False
        if self.scan_thread:
            self.scan_thread.join()

    def _scan_loop(self):
        """Continuously scan for modems."""
        while self.running:
            try:
                self._scan_modems()
            except Exception as e:
                if isinstance(e, serial.serialutil.SerialException) and "could not open port" in str(e):
                    # Ignore serial port errors, they can happen when a device is temporarily unavailable
                    logger.debug(f"Serial port error (likely device was unplugged): {e}")
                    continue
                logger.error(f"Error scanning modems: {e}")
            time.sleep(5)  # Scan every 5 seconds

    def _scan_modems(self):
        """Scan for USB modems."""
        current_ports = set()
        
        # List all COM ports
        for port in serial.tools.list_ports.comports():
            logger.debug(f"Found port: {port.device} - {port.description}")
            
            if self._is_gsm_modem(port):
                current_ports.add(port.device)
                if port.device not in self.modems or self.modems[port.device]['status'] == 'error':
                    self._add_modem(port)
        
        # Remove disconnected modems
        disconnected = set(self.modems.keys()) - current_ports
        for port in disconnected:
            self._remove_modem(port)

    def _is_diagnostic_port(self, port) -> bool:
        """Check if this is a diagnostic or management port."""
        if not hasattr(port, 'description'):
            return False
            
        diagnostic_keywords = [
            'DIAGNOSTIC',
            'DIAG',
            'NMEA',
            'AT INTERFACE',
            'MANAGEMENT',
            'QCDM',
            'QXDM',
            'PCUI',
            'LOGGING',
            'DM PORT',
            'ADB',
            'QDLoader'
        ]
        
        description = port.description.upper()
        return any(keyword in description for keyword in diagnostic_keywords)

    def _is_franklin_t9(self, port) -> bool:
        """
        Specifically check if a port is a Franklin T9 modem.
        Franklin T9 modems have specific identifiers:
        - VID: 05C6 (Qualcomm)
        - Description contains "Qualcomm HS-USB"
        - Not a diagnostic port
        """
        if not hasattr(port, 'description') or not hasattr(port, 'vid'):
            return False

        is_qualcomm = (
            hasattr(port, 'vid') and 
            port.vid == 0x05C6  # Qualcomm's Vendor ID
        )
        
        has_correct_description = (
            "Qualcomm HS-USB" in port.description and
            not self._is_diagnostic_port(port)
        )
        
        if is_qualcomm and has_correct_description:
            logger.debug(f"Confirmed Franklin T9 modem on port {port.device}")
            logger.debug(f"VID: {port.vid:04X}, Description: {port.description}")
            return True
            
        return False

    def _is_gsm_modem(self, port) -> bool:
        """Check if a port is likely a GSM modem."""
        if not hasattr(port, 'description'):
            return False

        description = str(port.description)
        logger.debug(f"Checking port {port.device} - Description: {description}")

        # Check specifically for Franklin T9 modem first
        if self._is_franklin_t9(port):
            return True

        # Common USB IDs for GSM modems
        gsm_ids = [
            "12D1",  # Huawei
            "19D2",  # ZTE
            "2C7C",  # Quectel
            "1E0E",  # Qualcomm
            "0403",  # FTDI
            "067B",  # Prolific
            "0483",  # STMicroelectronics
            "1A86",  # QinHeng Electronics
            "05C6",  # Qualcomm USB modem
        ]
        
        if not hasattr(port, 'vid'):
            return False
            
        # Convert VID to hex string and compare
        vid_hex = f"{port.vid:04X}" if port.vid else ""
        
        # Check VID and product description
        is_modem = (vid_hex in gsm_ids and 
                   not self._is_diagnostic_port(port) and
                   (hasattr(port, 'product') and 
                    any(x in str(port.product).upper() for x in ['MODEM', 'GSM', 'MOBILE', 'WWAN', '3G', '4G', 'LTE'])))
        
        if is_modem:
            logger.debug(f"Found GSM modem: {port.device}")
        return is_modem

    def _validate_phone_number(self, number: str) -> bool:
        """Validate phone number format."""
        if not number:
            return False
            
        # Remove common phone number formatting including + prefix
        clean_number = re.sub(r'[\s\-\(\)\+]', '', number)
        
        # Check if it's exactly 11 digits (country code + number)
        is_valid = clean_number.isdigit() and len(clean_number) == 11
        logger.debug(f"Phone number validation: {number} -> {clean_number} -> {is_valid}")
        return clean_number if is_valid else None  # Return cleaned number if valid

    def _add_modem(self, port):
        """Initialize and add a new modem."""
        try:
            logger.debug(f"Attempting to add modem on port {port.device}")
            modem = serial.Serial(port.device, baudrate=115200, timeout=1)
            
            # Initialize modem
            commands = [
                ('AT', 0.1),  # Basic AT command
                ('ATE0', 0.1),  # Turn off echo
                ('AT+CMEE=2', 0.1),  # Extended error reporting
                ('AT+CIMI', 0.1),  # Get IMSI
                ('AT+CCID', 0.1),  # Get ICCID
                ('AT+CREG?', 0.1),  # Get Network Registration Status
                ('AT+CNUM', 0.1),  # Get phone number
                ('AT+COPS?', 0.1),  # Get carrier
                ('AT+CGMM', 0.1),  # Get model number
                ('AT+CGMR', 0.1),  # Get firmware version
            ]
            
            responses = {}
            for cmd, delay in commands:
                modem.write(f"{cmd}\r\n".encode())
                time.sleep(delay)
                response = modem.read_all().decode('utf-8', errors='ignore')
                responses[cmd] = response
                logger.debug(f"Command {cmd} response: {response}")
            
            # Parse responses
            imsi = self._parse_at_response(responses['AT+CIMI'], '+CIMI')
            iccid = self._parse_at_response(responses['AT+CCID'], '+CCID')
            phone = self._parse_at_response(responses['AT+CNUM'], '+CNUM')
            registration_status = self._parse_at_response(responses['AT+CREG?'], '+CREG')
            carrier = self._parse_at_response(responses['AT+COPS?'], '+COPS')
            model = self._parse_at_response(responses['AT+CGMM'], '+CGMM')
            firmware = self._parse_at_response(responses['AT+CGMR'], '+CGMR')
            
            logger.debug(f"Parsed responses - IMSI: {imsi}, ICCID: {iccid}, Phone: {phone}, " +
                        f"Reg Status: {registration_status}, Carrier: {carrier}, " +
                        f"Model: {model}, Firmware: {firmware}")

            # Determine if this is a Franklin T9 modem
            is_franklin = self._is_franklin_t9(port)
            
            # Additional Franklin T9 verification through AT commands
            if is_franklin:
                if model and "T9" in model:
                    logger.info(f"Confirmed Franklin T9 through model number: {model}")
                else:
                    logger.warning(f"Port appears to be Franklin T9 but model number doesn't match: {model}")
            
            # Determine modem status
            if is_franklin:
                status = 'active'  # Franklin T9 modems are always active
            else:
                status = 'active' if registration_status and '0,1' in registration_status or '0,5' in registration_status else 'not_registered'
            if 'ERROR' in responses['AT']:
                status = 'error'

            # Only add modem if we got a valid phone number or it's a Franklin T9
            validated_phone = self._validate_phone_number(phone)
            
            if validated_phone or is_franklin:
                modem_info = {
                    'port': port.device,
                    'imsi': imsi or 'Unknown',
                    'iccid': iccid or 'Unknown',                    
                    'phone': validated_phone or 'Unknown',
                    'status': status,
                    'last_seen': time.time(),
                    'manufacturer': port.manufacturer or 'Unknown',
                    'product': port.product or port.description or 'Unknown',
                    'model': model or 'Unknown',
                    'firmware': firmware or 'Unknown',
                    'vid': f"{port.vid:04X}" if port.vid else 'Unknown',
                    'pid': f"{port.pid:04X}" if port.pid else 'Unknown',
                    'carrier': carrier or 'Unknown',
                    'type': 'Franklin T9' if is_franklin else 'Generic GSM',
                    'operator': 'physic'  # Always set operator to 'physic'
                }
                
                self.modems[port.device] = modem_info
                self.connected_modems.add(port.device)  # Mark as connected
                
                # Register with server if available
                if self.server:
                    self.server.register_modem(validated_phone or port.device, modem_info) # Use validated phone if available
                    logger.info(f"Registered modem {validated_phone or port.device} with server")
                
                logger.info(f"Added modem: {modem_info}")
            else:
                logger.debug(f"Skipping port {port.device}: No valid phone number and not a Franklin T9 modem")

            modem.close()
            
        except Exception as e:
            logger.error(f"Error adding modem on port {port.device}: {e}")

    def _remove_modem(self, port):
        """Remove a disconnected modem."""
        if port in self.modems:
            logger.info(f"Removed modem: {self.modems[port]}")
            self.modems.pop(port)

    def _parse_at_response(self, response: str, command: str) -> Optional[str]:
        """Parse AT command response to extract relevant information."""
        if not response:
            return None
            
        lines = response.split('\r\n')
        for line in lines:
            if command in line:
                # Extract the value after the command
                parts = line.split(':')
                if len(parts) > 1:
                    value = parts[1].strip()
                    # Handle CNUM response format
                    if command == '+CNUM' and ',' in value:
                        number_parts = value.split(',')
                        if len(number_parts) >= 2:
                            # Remove + prefix if present
                            number = number_parts[1].strip('"').lstrip('+')
                            return number
                    # Handle COPS response format
                    elif command == '+COPS' and ',' in value:
                        cops_parts = value.split(',')
                        if len(cops_parts) >= 3:
                            return cops_parts[2].strip('"')
                    return value
                
            # Handle case where response is just the value
            elif line.strip() and not any(x in line for x in ['OK', 'ERROR']):
                return line.strip()
        return None

    def get_active_modems(self) -> List[Dict]:
        """Get list of active modems."""
        return list(self.modems.values())

    def get_modem_by_phone(self, phone: str) -> Optional[Dict]:
        """Get modem info by phone number"""
        return next((m for m in self.modems.values() if m['phone'] == phone), None)

    def get_all_device_info(self) -> List[Dict]:
        """Get information about all connected devices."""
        devices = []
        for port, info in self.modems.items():
            device_info = {
                'device_name': info.get('product', 'Unknown'),
                'com_port': port,
                'imei': info.get('imsi', 'Unknown'),
                'iccid': info.get('iccid', 'Unknown'),
                'phone_number': info.get('phone', 'Unknown'),
                'carrier': info.get('carrier', 'Unknown'),
                'status': 'Connected' if port in self.connected_modems else 'Disconnected'
            }
            devices.append(device_info)
        return devices

    def check_sms(self, port: str) -> List[Dict]:
        """Check for SMS messages on a specific modem."""
        try:
            if port not in self.modems:
                logger.error(f"Port {port} not found in modems")
                return []

            modem = serial.Serial(port, baudrate=115200, timeout=1)
            messages = []

            # Set text mode
            modem.write(b'AT+CMGF=1\r\n')
            time.sleep(0.1)
            modem.read_all()  # Clear buffer

            # List all messages
            modem.write(b'AT+CMGL="ALL"\r\n')
            time.sleep(0.5)
            response = modem.read_all().decode('utf-8', errors='ignore')

            # Parse messages
            msg_lines = response.split('\r\n')
            current_msg = None

            for line in msg_lines:
                if line.startswith('+CMGL:'):
                    if current_msg:
                        messages.append(current_msg)
                    # Parse message header
                    parts = line.split(',')
                    if len(parts) >= 4:
                        current_msg = {
                            'index': parts[0].split(':')[1].strip(),
                            'status': parts[1].strip('"'),
                            'sender': parts[2].strip('"'),
                            'timestamp': parts[4].strip('"') if len(parts) > 4 else '',
                            'text': ''
                        }
                elif line.strip() and current_msg:
                    current_msg['text'] = line.strip()

            if current_msg:
                messages.append(current_msg)

            modem.close()
            return messages

        except Exception as e:
            logger.error(f"Error checking SMS on port {port}: {e}")
            return []

    def send_at_command(self, port: str, command: str) -> str:
        """Send AT command to modem and return response."""
        try:
            if port not in self.modems:
                return "Error: Port not found"

            modem = serial.Serial(port, baudrate=115200, timeout=1)
            
            # Add AT prefix if not present
            if not command.upper().startswith('AT'):
                command = 'AT' + command

            # Send command
            modem.write(f"{command}\r\n".encode())
            time.sleep(0.5)
            response = modem.read_all().decode('utf-8', errors='ignore')
            
            modem.close()
            return response.strip()

        except Exception as e:
            logger.error(f"Error sending AT command to port {port}: {e}")
            return f"Error: {str(e)}"

    def find_franklin_t9_devices(self) -> List[str]:
        """Find Franklin T9 modems."""
        new_ports = []
        for port in serial.tools.list_ports.comports():
            if "Qualcomm HS-USB" in port.description and not self._is_diagnostic_port(port):
                if port.device not in self.modems:
                    new_ports.append(port.device)
        return new_ports

    def connect_all(self):
        """Connect to all modems."""
        for port in self.modems:
            try:
                modem = serial.Serial(port, baudrate=115200, timeout=1)
                modem.close()
                self.connected_modems.add(port)
                logger.info(f"Connected to modem on port {port}")
            except Exception as e:
                logger.error(f"Failed to connect to modem on port {port}: {e}")

    def disconnect_all(self):
        """Disconnect from all modems."""
        self.connected_modems.clear()
        logger.info("Disconnected from all modems")

    def _get_imei(self, port) -> str:
        """Get IMEI from modem."""
        try:
            with serial.Serial(port.device, baudrate=115200, timeout=1) as modem:
                modem.write(b'AT+CGSN\r\n')
                time.sleep(0.1)
                response = modem.read_all().decode('utf-8', errors='ignore')
                # Extract IMEI from response
                match = re.search(r'\d{15}', response)
                return match.group(0) if match else 'N/A'
        except Exception as e:
            logger.error(f"Error getting IMEI: {e}")
            return 'N/A'

    def _get_phone_number(self, port) -> str:
        """Get phone number from modem."""
        try:
            with serial.Serial(port.device, baudrate=115200, timeout=1) as modem:
                modem.write(b'AT+CNUM\r\n')
                time.sleep(0.1)
                response = modem.read_all().decode('utf-8', errors='ignore')
                # Extract phone number from response
                match = re.search(r'\+1(\d{10})', response)
                return match.group(1) if match else 'N/A'
        except Exception as e:
            logger.error(f"Error getting phone number: {e}")
            return 'N/A'

    def _get_signal_strength(self, port) -> str:
        """Get signal strength from modem."""
        try:
            with serial.Serial(port.device, baudrate=115200, timeout=1) as modem:
                modem.write(b'AT+CSQ\r\n')
                time.sleep(0.1)
                response = modem.read_all().decode('utf-8', errors='ignore')
                # Extract signal strength from response
                match = re.search(r'\+CSQ:\s*(\d+),', response)
                if match:
                    csq = int(match.group(1))
                    if csq == 99:
                        return 'No Signal'
                    # Convert CSQ to percentage (0-31 scale)
                    percentage = min(100, int((csq / 31) * 100))
                    return f"{percentage}%"
                return 'N/A'
        except Exception as e:
            logger.error(f"Error getting signal strength: {e}")
            return 'N/A'

    def get_modems(self) -> Dict[str, Dict]:
        """Get all registered modems."""
        return self.modems