import logging
import time
import threading
import serial
from serial.tools import list_ports
import re
from typing import Dict, Optional, List
from config import config
from modems.franklin_t9 import FranklinT9Modem
from modems.novatel_551l import Novatel551LModem

logger = logging.getLogger(__name__)

class ModemManager:
    def __init__(self, server=None):
        """Initialize ModemManager."""
        self.modems = {}  # port -> modem_info
        self.server = server
        self.running = False
        self.scan_thread = None
        self.scan_interval = 10  # seconds
        self.connected_modems = set()  # Track connected modems
        
    def _scan_modems(self):
        """Scan for available modems."""
        try:
            logger.info("\n=== SCANNING FOR MODEMS ===")
            processing_ports = set()
            
            ports = list_ports.comports()
            # Accept both Qualcomm (Franklin T9) and Novatel devices
            current_ports = {p.device: p for p in ports if (
                (p.vid == 0x05C6 and "Qualcomm HS-USB" in p.description) or  # Franklin T9
                (p.vid == 0x1410 and "modem" in p.description.lower())  # Novatel 551L - look for any modem port
            )}
            
            logger.info(f"Found {len(current_ports)} potential modem ports")
            
            # Remove disconnected modems first
            disconnected = set(self.modems.keys()) - set(current_ports.keys())
            for port in disconnected:
                logger.info(f"Removing disconnected modem: {port}")
                self.modems.pop(port)
            
            # Add or update modems
            for port_name, port in current_ports.items():
                # Skip if port is already being processed
                if port_name in processing_ports:
                    continue
                    
                # Skip diagnostic and NMEA ports
                if any(x in port.description.upper() for x in ['DIAGNOSTIC', 'NMEA', 'LOGGING']):
                    logger.debug(f"Skipping diagnostic/NMEA port: {port_name}")
                    continue
                
                # Only initialize new modems or update existing ones after scan_interval
                current_time = time.time()
                if (port_name not in self.modems or 
                    current_time - self.modems[port_name].get('last_seen', 0) >= self.scan_interval):
                    
                    logger.info(f"\nProcessing port: {port_name}")
                    if port_name in self.modems:
                        logger.info(f"Previous status: {self.modems[port_name].get('status')}")
                        logger.info("Updating modem info...")
                    else:
                        logger.info("New modem detected")
                    
                    # Mark port as being processed
                    processing_ports.add(port_name)
                    
                    try:
                        modem_info = self._add_modem(port)
                        if modem_info:
                            # Log status change if any
                            old_status = self.modems[port_name].get('status') if port_name in self.modems else None
                            new_status = modem_info.get('status')
                            
                            if old_status != new_status:
                                logger.info(f"Status changed for {port_name}: {old_status} -> {new_status}")
                                if new_status != 'active' and modem_info.get('iccid') and modem_info.get('network_status') in ['registered', 'roaming']:
                                    logger.info("Requirements check:")
                                    logger.info(f"- ICCID: {modem_info.get('iccid', 'Missing')}")
                                    logger.info(f"- Network: {modem_info.get('network_status', 'Missing')}")
                                    logger.info(f"- Phone: {modem_info.get('phone', 'Missing')}")
                            
                            if modem_info.get('status') != 'error':
                                self.modems[port_name] = modem_info
                                logger.info(f"Added/Updated modem: {port_name} (Status: {modem_info.get('status')})")
                            else:
                                # Only add errored modem if it's a new error
                                if port_name not in self.modems or self.modems[port_name].get('error') != modem_info.get('error'):
                                    self.modems[port_name] = modem_info
                                    logger.error(f"Error initializing modem {port_name}: {modem_info.get('error')}")
                    finally:
                        # Remove port from processing set even if there was an error
                        processing_ports.discard(port_name)
                else:
                    logger.debug(f"Skipping {port_name} - Recently updated")
            
            # Log final modem statuses
            logger.info("\n=== CURRENT MODEM STATUSES ===")
            for port, info in self.modems.items():
                logger.info(f"{port}: {info.get('status')} (ICCID: {'✓' if info.get('iccid') else '✗'}, "
                          f"Network: {info.get('network_status')}, Phone: {'✓' if info.get('phone') not in [None, 'Unknown'] else '✗'})")
            logger.info("===============================\n")
                
        except Exception as e:
            logger.error(f"Error scanning modems: {e}")
            logger.error("Full error details:", exc_info=True)
            
    def _is_diagnostic_port(self, port) -> bool:
        """Check if the port is a diagnostic port."""
        if not port or not port.description:
            return False
            
        # Check for common diagnostic port indicators
        diagnostic_indicators = [
            'DIAGNOSTIC',
            'NMEA',
            'LOGGING',
            'AT INTERFACE',
            'MODEM INTERFACE',
            'PCUI',
            'DM PORT'
        ]
        
        description_upper = port.description.upper()
        return any(indicator in description_upper for indicator in diagnostic_indicators)

    def _validate_phone_number(self, phone: str) -> str:
        """Less strict phone validation."""
        logger.info(f"\n=== VALIDATING PHONE NUMBER ===")
        logger.info(f"Input phone: {phone}")
        
        if not phone or phone == 'Unknown':
            logger.warning("✗ Phone is None or 'Unknown'")
            return None
            
        # Remove any non-digit characters
        clean_number = ''.join(filter(str.isdigit, phone))
        logger.info(f"Cleaned number: {clean_number}")
        
        # Must be at least 10 digits
        if len(clean_number) < 10:
            logger.warning(f" Too short ({len(clean_number)} digits): {clean_number}")
            return None
            
        # If it's 10 digits, add '1' prefix
        if len(clean_number) == 10:
            clean_number = '1' + clean_number
            logger.info(f"Added '1' prefix: {clean_number}")
        # If it's longer than 10 digits but doesn't start with 1, add it
        elif not clean_number.startswith('1'):
            clean_number = '1' + clean_number
            logger.info(f"Added '1' prefix to longer number: {clean_number}")
            
        logger.info(f"✓ Valid phone number: {clean_number}\n")
        return clean_number

    def _check_network_registration(self, ser) -> str:
        """Check network registration with retries and detailed diagnostics."""
        logger.info("\n=== CHECKING NETWORK REGISTRATION ===")
        max_retries = 3
        retry_delay = 2  # seconds
        
        # First check signal quality
        ser.write(b'AT+CSQ\r\n')
        time.sleep(0.5)
        signal_response = ser.read_all().decode('utf-8', errors='ignore')
        signal_quality = self._parse_signal_quality(signal_response)
        logger.info(f"Signal Quality: {signal_quality}%")
        
        if signal_quality < 10:
            logger.warning("⚠️ Very weak signal - may affect registration")
        
        # Check if SIM is locked
        ser.write(b'AT+CPIN?\r\n')
        time.sleep(0.5)
        pin_response = ser.read_all().decode('utf-8', errors='ignore')
        if 'READY' not in pin_response:
            logger.error("✗ SIM card not ready or PIN locked")
            return 'not_registered'
        
        # Check operator selection
        ser.write(b'AT+COPS?\r\n')
        time.sleep(0.5)
        cops_response = ser.read_all().decode('utf-8', errors='ignore')
        logger.info(f"Current Operator: {cops_response.strip()}")
        
        for attempt in range(max_retries):
            try:
                logger.info(f"\nAttempt {attempt + 1}/{max_retries}")
                
                # Clear input buffer
                ser.reset_input_buffer()
                
                # Send registration check command
                ser.write(b'AT+CREG?\r\n')
                time.sleep(0.5)
                response = ser.read_all().decode('utf-8', errors='ignore')
                
                status = self._parse_network_registration(response)
                logger.info(f"Registration Status: {status}")
                
                if status == 'not_registered':
                    logger.info("Not registered, checking extended status...")
                    # Check extended registration info
                    ser.write(b'AT+CREG=2\r\n')  # Enable extended registration info
                    time.sleep(0.5)
                    ser.write(b'AT+CREG?\r\n')
                    time.sleep(0.5)
                    ext_response = ser.read_all().decode('utf-8', errors='ignore')
                    logger.info(f"Extended Registration Info: {ext_response.strip()}")
                    
                elif status == 'searching':
                    logger.info("Still searching for network...")
                    
                elif status == 'denied':
                    logger.error("✗ Registration denied by network")
                    return status
                    
                elif status in ['registered', 'roaming']:
                    logger.info(f"✓ Successfully registered: {status}")
                    return status
                    
                if attempt < max_retries - 1:
                    logger.info(f"Waiting {retry_delay}s before retry...")
                    time.sleep(retry_delay)
                    
            except Exception as e:
                logger.error(f"Error checking registration: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    
        logger.warning("✗ Failed to register after all retries")
        return 'not_registered'

    def _add_modem(self, port):
        """Initialize and add a new modem."""
        ser = None
        modem = None
        try:
            logger.info(f"\n=== ADDING MODEM ON {port.device} ===")
    
            # Skip if it's a diagnostic port
            if self._is_diagnostic_port(port):
                logger.debug(f"Skipping diagnostic port: {port.device}")
                return None
    
            # Create appropriate modem instance based on device type
            if port.vid == 0x1410 and "modem" in port.description.lower():  # Novatel Wireless modem
                modem = Novatel551LModem(port.device)
            else:  # Default to Franklin T9
                modem = FranklinT9Modem(port.device)
    
            if not modem.initialize_modem():
                return {
                    'status': 'error',
                    'error': 'Failed to initialize modem',
                    'last_seen': time.time()
                }
    
            # Get modem info
            modem_info = {
                'status': 'initializing',
                'imei': modem.imei,
                'iccid': modem.iccid,
                'phone': modem.phone,  # Add phone number to modem info
                'network_status': modem.network_status,
                'signal_quality': modem.signal_quality,
                'carrier': modem.operator,  # Use 'carrier' instead of 'operator'
                'last_seen': time.time()
            }
    
            # Update status based on requirements
            if modem_info['iccid'] != 'Unknown' and modem_info['network_status'] in ['registered', 'roaming']:
                modem_info['status'] = 'active'
            else:
                modem_info['status'] = 'inactive'
    
            return modem_info
    
        except Exception as e:
            logger.error(f"Error adding modem: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'last_seen': time.time()
            }
        finally:
            if modem:
                modem.cleanup()

    def _parse_at_response(self, response: str, command: str) -> Optional[str]:
        """Parse AT command response to extract relevant information."""
        if not response:
            return None
    
        try:
            lines = response.split('\r\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue
    
                if command in line:
                    # Extract the value after the command
                    parts = line.split(':')
                    if len(parts) > 1:
                        value = parts[1].strip()
                        # Handle CNUM response format
                        if command == '+CNUM' and ',' in value:
                            number_parts = value.split(',')
                            if len(number_parts) >= 2:
                                # Remove quotes and any non-digit characters except +
                                number = ''.join(c for c in number_parts[1].strip('"') if c.isdigit() or c == '+')
                                # Ensure it starts with +1 for US numbers
                                if not number.startswith('+'):
                                    number = '+' + number
                                if not number.startswith('+1'):
                                    number = '+1' + number.lstrip('+')
                                logger.info(f"Parsed phone number: {number}")
                                return number
                        # Handle COPS response format
                        elif command == '+COPS' and ',' in value:
                            return value  # Return the raw response for COPS command
                        # For other commands, return the value if it looks valid
                        elif value and not any(x in value for x in ['ERROR', 'OK']):
                            return value
    
                # Handle case where response is just the value
                elif line and not any(x in line for x in ['OK', 'ERROR', '+', 'AT']):
                    # For IMSI/ICCID, validate it's a number
                    if command in ['+CIMI', '+CCID'] and not line.isdigit():
                        continue
                    return line
    
        except Exception as e:
            logger.error(f"Error parsing AT response for {command}: {e}")
            logger.error(f"Response was: {response}")
    
        return None
            
    def _parse_ccid_response(self, response: str) -> Optional[str]:
        """Parse CCID (SIM card number) from various AT command responses."""
        try:
            if not response:
                return None
                
            # Split response into lines and clean them
            lines = [line.strip() for line in response.split('\r\n') if line.strip()]
            
            for line in lines:
                # Remove any non-digit characters for checking
                digits_only = ''.join(filter(str.isdigit, line))
                
                # If we find a 19-20 digit number anywhere in the response, that's likely the ICCID
                if len(digits_only) >= 19 and len(digits_only) <= 20:
                    return digits_only
                
                # Check various response formats
                prefixes = ['+CCID:', '^ICCID:', '+ICCID:', '+QCCID:', '$QCCID:', 'ICCID:', '+CRSM:']
                for prefix in prefixes:
                    if prefix in line:
                        # Split on the prefix and take the latter part
                        value = line.split(prefix)[-1].strip()
                        # Clean up any quotes, spaces, or commas
                        value = value.strip('"').strip().split(',')[0]
                        # Extract just the digits
                        digits = ''.join(filter(str.isdigit, value))
                        if len(digits) >= 19 and len(digits) <= 20:
                            return digits
                            
            logger.debug(f"Could not parse CCID from response: {response}")
            return None
            
        except Exception as e:
            logger.error(f"Error parsing CCID response: {e}")
            return None

    def check_sms(self, port):
        """Check for new SMS messages on the specified port."""
        ser = None
        try:
            # Validate port exists
            if port not in self.modems:
                logger.error(f"Port {port} not found in modems")
                return []

            # Try to open and configure port
            try:
                ser = serial.Serial(
                    port=port,
                    baudrate=115200,
                    timeout=1,
                    writeTimeout=1,
                    exclusive=True  # Use exclusive access for Windows compatibility
                )
            except serial.SerialException as e:
                if "in use" in str(e).lower():
                    logger.warning(f"Port {port} is busy")
                else:
                    logger.error(f"Failed to open port {port}: {e}")
                return []

            try:
                # Clear any pending data
                ser.reset_input_buffer()
                
                # Initialize modem
                ser.write(b'AT\r\n')
                time.sleep(0.1)
                ser.write(b'AT+CMGF=1\r\n')  # Set text mode
                time.sleep(0.1)
                ser.write(b'AT+CSCS="GSM"\r\n')  # Set GSM character set
                time.sleep(0.1)
                
                # Read SMS messages
                ser.write(b'AT+CMGL="ALL"\r\n')
                time.sleep(1)  # Wait for response
                
                # Try different encodings
                raw_response = ser.read_all()
                response = None
                
                for encoding in ['utf-8', 'ascii', 'iso-8859-1', 'cp1252']:
                    try:
                        response = raw_response.decode(encoding, errors='replace')
                        if response:
                            break
                    except Exception as e:
                        logger.debug(f"Failed to decode with {encoding}: {e}")
                        continue
                
                if not response:
                    logger.error(f"Could not decode modem response with any encoding")
                    return []
                
                messages = []
                
                # Parse SMS messages
                lines = response.split('\r\n')
                i = 0
                while i < len(lines):
                    line = lines[i].strip()
                    if line.startswith('+CMGL:'):
                        try:
                            # Parse message header
                            parts = line.split(',')
                            if len(parts) >= 4:
                                msg_id = parts[0].split(':')[1].strip()
                                status = parts[1].strip('"')
                                sender = parts[2].strip('"')
                                timestamp = parts[3].strip('"')
                                
                                # Read message text (next line)
                                i += 1
                                if i < len(lines):
                                    text = lines[i].strip()
                                    # Replace any invalid characters
                                    text = ''.join(char if ord(char) < 128 else '?' for char in text)
                                    
                                    messages.append({
                                        'id': msg_id,
                                        'status': status,
                                        'sender': sender,
                                        'timestamp': timestamp,
                                        'text': text
                                    })
                                    
                                    # Delete processed message
                                    ser.write(f'AT+CMGD={msg_id}\r\n'.encode())
                                    time.sleep(0.1)
                                    logger.info(f"Successfully processed SMS from {sender}")
                        except Exception as e:
                            logger.error(f"Error parsing SMS message: {e}")
                    i += 1
                            
                return messages
                
            finally:
                # Make sure port is closed
                if ser and ser.is_open:
                    try:
                        ser.close()
                    except:
                        pass
                
        except Exception as e:
            logger.error(f"Error checking SMS on port {port}: {e}")
            # Make sure port is closed on error
            if ser and ser.is_open:
                try:
                    ser.close()
                except:
                    pass
            return []
            
    def handle_sms_received(self, port: str, sender: str, text: str) -> bool:
        """Handle received SMS message."""
        try:
            logger.info("========== NEW SMS RECEIVED ==========")
            logger.info(f"Port: {port}")
            logger.info(f"Sender: {sender}")
            logger.info(f"Text: {text}")
            logger.info(f"Current modems: {self.modems}")
            
            # Find modem by port
            modem = self.modems.get(port)
            if not modem:
                logger.error(f"No modem found for port {port}")
                return False
                
            logger.info(f"Found modem: {modem}")
            
            # Get phone number, ensuring proper format
            phone = modem.get('phone', '')
            if not phone or phone == 'Unknown':
                logger.error(f"No phone number for modem on port {port}")
                return False
                
            # Ensure proper phone number format for US numbers
            phone = phone.lstrip('+').lstrip('1')  # Remove any existing prefixes
            phone = f"+1{phone}"  # Add +1 prefix
            
            logger.info(f"Phone number: {phone}")
            
            # Forward to server
            if self.server:
                logger.info("Forwarding SMS to server...")
                return self.server.handle_incoming_sms(phone, sender, text)
            else:
                logger.error("No server configured")
                return False
                
        except Exception as e:
            logger.error(f"Error handling SMS: {e}")
            logger.error("Full error details:", exc_info=True)
            return False
            
    def _scan_loop(self):
        """Main scanning loop."""
        while self.running:
            try:
                # Scan for new modems
                self._scan_modems()
                
                # Check each modem for SMS only if it's not being initialized
                for port in list(self.modems.keys()):
                    if self.modems[port].get('status') == 'active':  # Only check active modems
                        messages = self.check_sms(port)
                        for msg in messages:
                            try:
                                # Get phone number for this port
                                phone = self.modems[port].get('phone')
                                if phone:
                                    self.handle_sms_received(port, msg['sender'], msg['text'])
                            except Exception as e:
                                logger.error(f"Error handling SMS message: {e}")
                        
            except Exception as e:
                logger.error(f"Error in scan loop: {e}")
                
            # Wait for next scan
            time.sleep(self.scan_interval)
            
    def start(self):
        """Start the modem manager."""
        if not self.running:
            self.running = True
            self.scan_thread = threading.Thread(target=self._scan_loop)
            self.scan_thread.daemon = True
            self.scan_thread.start()
            logger.info("ModemManager started")
            
    def stop(self):
        """Stop the modem manager."""
        self.running = False
        if self.scan_thread:
            self.scan_thread.join()
            logger.info("ModemManager stopped")

    def _parse_network_registration(self, response: str) -> str:
        """Parse network registration status from AT+CREG? response."""
        try:
            if not response:
                return 'unknown'
                
            # Look for +CREG: n,stat pattern
            match = re.search(r'\+CREG:\s*\d,(\d)', response)
            if match:
                status_code = match.group(1)
                return {
                    '0': 'not_registered',
                    '1': 'registered',
                    '2': 'searching',
                    '3': 'denied',
                    '4': 'unknown',
                    '5': 'roaming'
                }.get(status_code, 'unknown')
            
            return 'unknown'
        except Exception as e:
            logger.error(f"Error parsing network registration: {e}")
            return 'unknown'

    def _parse_signal_quality(self, response: str) -> int:
        """Parse signal quality from AT+CSQ response."""
        try:
            if not response:
                return 0
                
            # Look for +CSQ: rssi,ber pattern
            match = re.search(r'\+CSQ:\s*(\d+),', response)
            if match:
                rssi = int(match.group(1))
                # Convert to percentage (0-31 range to 0-100)
                if rssi == 99:  # 99 means unknown
                    return 0
                return min(100, int((rssi / 31) * 100))
            
            return 0
        except Exception as e:
            logger.error(f"Error parsing signal quality: {e}")
            return 0

    def _parse_imei_response(self, response: str) -> Optional[str]:
        """Parse IMEI from AT+GSN or AT+CGSN response."""
        try:
            if not response:
                return None
                
            # Split response into lines and clean them
            lines = [line.strip() for line in response.split('\r\n') if line.strip()]
            
            for line in lines:
                # IMEI should be exactly 15 digits
                digits_only = ''.join(filter(str.isdigit, line))
                if len(digits_only) == 15:
                    logger.debug(f"Found valid IMEI: {digits_only}")
                    return digits_only
                    
            logger.debug(f"Could not parse IMEI from response: {response}")
            return None
            
        except Exception as e:
            logger.error(f"Error parsing IMEI response: {e}")
            return None