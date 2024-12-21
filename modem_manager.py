import logging
import time
import threading
import serial
from serial.tools import list_ports
import re
from typing import Dict, Optional, List
from config import config

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
            # Track ports being processed to avoid duplicates
            processing_ports = set()
            
            # Get current available ports
            ports = list_ports.comports()
            current_ports = {p.device: p for p in ports if (p.vid == 0x05C6 or  # Qualcomm
                                                          p.vid == 0x2C7C or  # Quectel
                                                          p.vid == 0x1782)}   # SimCom
            
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
        try:
            logger.info(f"\n=== ADDING MODEM ON {port.device} ===")
            
            # Skip if it's a diagnostic port
            if self._is_diagnostic_port(port):
                logger.debug(f"Skipping diagnostic port: {port.device}")
                return None
            
            try:
                # Try to open the port with a shorter timeout first
                ser = serial.Serial(
                    port=port.device,
                    baudrate=115200,
                    timeout=1,  # Increased from 0.5
                    writeTimeout=1,  # Increased from 0.5
                    exclusive=True
                )
                
            except serial.SerialException as e:
                if "in use" in str(e).lower() or "access is denied" in str(e).lower():
                    logger.warning(f"Port {port.device} is busy or access denied, skipping")
                else:
                    logger.error(f"Failed to open port {port.device}: {e}")
                return None
            except Exception as e:
                logger.error(f"Unexpected error opening port {port.device}: {e}")
                return None
            
            # Initialize modem with expanded AT commands
            commands = [
                ('AT', 0.2),  # Increased delay
                ('ATE0', 0.2),
                ('AT+CMEE=2', 0.2),
                ('AT+GSN', 0.2),
                ('AT+CGSN', 0.2),
                ('AT+CIMI', 0.2),
                ('AT+CCID', 1.0),
                ('AT^ICCID?', 1.0),
                ('AT+QCCID', 1.0),
                ('AT+ZGETICCID', 1.0),
                ('AT$QCCID?', 1.0),
                ('AT+ICCID', 1.0),
                ('AT+CRSM=176,12258,0,0,10', 1.0),
                ('AT+CREG?', 0.2),
                ('AT+CNUM', 0.2),
                ('AT+COPS?', 0.2),
                ('AT+CSQ', 0.2),
            ]
            
            responses = {}
            for cmd, delay in commands:
                try:
                    # Clear input buffer before each command
                    ser.reset_input_buffer()
                    ser.write(f"{cmd}\r\n".encode())
                    time.sleep(delay)
                    response = ser.read_all().decode('utf-8', errors='ignore')
                    responses[cmd] = response
                    logger.debug(f"Command {cmd} response: {response}")
                except Exception as e:
                    logger.error(f"Error sending command {cmd}: {e}")
                    continue

            # Parse responses with more lenient validation
            imei = (self._parse_imei_response(responses['AT+GSN']) or 
                   self._parse_imei_response(responses['AT+CGSN']))
            
            imsi = self._parse_at_response(responses['AT+CIMI'], '+CIMI')
            
            # Try all ICCID responses
            iccid = None
            for cmd in [
                'AT+CCID',
                'AT^ICCID?',
                'AT+QCCID',
                'AT+ZGETICCID',
                'AT$QCCID?',
                'AT+ICCID',
                'AT+CRSM=176,12258,0,0,10'
            ]:
                if cmd in responses:
                    iccid = self._parse_ccid_response(responses[cmd])
                    if iccid:
                        logger.info(f"✓ Got ICCID using {cmd}: {iccid}")
                        break

            # Check network registration with retries
            reg_status = self._check_network_registration(ser)
            
            # Get phone number and carrier
            phone = self._parse_at_response(responses['AT+CNUM'], '+CNUM')
            carrier = self._parse_at_response(responses['AT+COPS?'], '+COPS')
            signal_quality = self._parse_signal_quality(responses['AT+CSQ'])

            # Determine modem status with more lenient checks
            status = 'connected'
            logger.info(f"\n=== MODEM STATUS CHECK for {port.device} ===")
            logger.info(f"Initial status: {status}")
            
            # Check SIM (more lenient)
            if iccid:
                status = 'sim_ready'
                logger.info(f"✓ SIM present - Status updated to: {status}")
                
                # Check network FIRST (using retry results)
                if reg_status in ['registered', 'roaming']:
                    status = 'registered'
                    logger.info(f"✓ Network registered - Status updated to: {status}")
                    
                    # Only validate phone number if we're registered
                    phone = self._parse_at_response(responses['AT+CNUM'], '+CNUM')
                    logger.info(f"Raw phone number from network: {phone}")
                    
                    validated_phone = self._validate_phone_number(phone)
                    if validated_phone:
                        status = 'active'
                        logger.info(f"✓ Valid phone number - Status updated to: {status}")
                        phone = validated_phone  # Use validated number
                    else:
                        logger.warning(f"✗ Invalid/missing phone number: {phone}")
                else:
                    # If not registered, any phone number is invalid
                    logger.warning(f"✗ Not registered on network. Status: {reg_status}")
                    phone = None  # Clear any phone number since we're not registered
            else:
                logger.warning(f"✗ No valid ICCID found")
                phone = None  # Clear any phone number since we don't have a valid SIM
            
            logger.info(f"=== FINAL STATUS: {status} ===\n")

            # Create modem info with phone number only if properly registered
            modem_info = {
                'port': port.device,
                'imei': imei or 'Unknown',
                'iccid': iccid or 'Unknown',
                'phone': phone or 'Unknown',
                'status': status,
                'last_seen': time.time(),
                'manufacturer': port.manufacturer or 'Unknown',
                'product': port.product or port.description or 'Unknown',
                'vid': f"{port.vid:04X}" if port.vid else 'Unknown',
                'pid': f"{port.pid:04X}" if port.pid else 'Unknown',
                'carrier': carrier or 'Unknown',
                'type': 'Franklin T9' if "Qualcomm HS-USB" in port.description else 'Generic GSM',
                'operator': 'physic',
                'signal_quality': signal_quality,
                'network_status': reg_status,
                'imsi': imsi or 'Unknown'
            }
            
            # Store in local modems dict
            self.modems[port.device] = modem_info
            self.connected_modems.add(port.device)
            
            # Register with server if active
            if self.server and status == 'active':
                try:
                    self.server.register_modem(port.device, modem_info)
                    logger.info(f"✓ Registered modem with server: {port.device}")
                except Exception as e:
                    logger.error(f"Error registering modem with server: {e}")
            
            return modem_info

        except Exception as e:
            logger.error(f"Error adding modem on port {port.device}: {e}")
            return None
            
        finally:
            if ser and ser.is_open:
                try:
                    ser.close()
                except Exception as e:
                    logger.error(f"Error closing port {port.device}: {e}")

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
                            cops_parts = value.split(',')
                            if len(cops_parts) >= 3:
                                return cops_parts[2].strip('"')
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