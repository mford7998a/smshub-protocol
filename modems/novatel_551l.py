import logging
from modems.modem_base import ModemBase
import serial
import time
import re
from serial.tools import list_ports

class Novatel551LModem(ModemBase):
    def __init__(self, port):
        super().__init__(port)
        self.is_open = False
        self.logger = logging.getLogger(__name__)
        self.ser = None
        self.imei = "Unknown"
        self.iccid = "Unknown"
        self.phone = "Unknown"
        self.network_status = "not_registered"
        self.signal_quality = 0
        self.operator = "Unknown"
        self.initialized = False
        self.vendor_id = 0x1410  # Novatel Wireless, Inc.
        self.product_id = 0xB001 # USB 551L specific
        
    @staticmethod
    def find_modem_port():
        """Find any available Novatel Wireless USB modem port."""
        try:
            # Get all COM ports
            ports = list_ports.comports()
            print("\nScanning for Novatel Wireless USB modem ports...")
            
            # Look for any Novatel Wireless port with "modem" in description
            modem_ports = []
            for port in ports:
                if (port.vid == 0x1410 and  # Novatel Wireless VID
                    "modem" in port.description.lower() and 
                    "novatel wireless" in port.description.lower()):
                    print(f"✓ Found Novatel Wireless modem on {port.device}: {port.description}")
                    modem_ports.append(port.device)
            
            if modem_ports:
                # Return the first available modem port
                print(f"Using modem port: {modem_ports[0]}")
                return modem_ports[0]
            
            print("✗ No Novatel Wireless modem ports found")
            return None
            
        except Exception as e:
            logging.error(f"Error finding Novatel modem port: {e}")
            return None
        
    def open_serial(self):
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
                time.sleep(1)
            
            # Try to find the correct modem port if not explicitly provided
            if not self.port:
                self.port = self.find_modem_port()
                if not self.port:
                    self.logger.error("Could not find Novatel modem port")
                    return False
            
            # Configure serial port based on USB descriptor
            self.ser = serial.Serial(
                port=self.port,
                baudrate=115200,
                timeout=2,
                exclusive=True,
                write_timeout=1
            )
            
            # Verify this is actually the modem port by sending an AT command
            try:
                self.ser.write(b'AT\r\n')
                time.sleep(0.5)
                response = self.ser.read_all().decode(errors='ignore')
                if 'OK' not in response:
                    self.logger.error(f"Port {self.port} did not respond to AT command")
                    self.ser.close()
                    return False
            except Exception as e:
                self.logger.error(f"Error verifying modem port: {e}")
                self.ser.close()
                return False
            
            self.is_open = True
            self.logger.info(f"Successfully opened Novatel modem port: {self.port}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to open serial port {self.port}: {str(e)}")
            self.is_open = False
            return False
            
    def close_serial(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.is_open = False 
        
    def _get_imei(self):
        """Get modem IMEI number."""
        try:
            # Try multiple IMEI commands as the modem supports different interfaces
            commands = ["AT+GSN", "AT+CGSN", "ATI"]
            for cmd in commands:
                success, response = self._send_at_command(cmd)
                if success and response:
                    for line in response.split('\n'):
                        line = line.strip()
                        if len(line) == 15 and line.isdigit():
                            return line
            return "Unknown"
        except Exception as e:
            self.logger.error(f"Error getting IMEI: {e}")
            return "Unknown"
            
    def _get_iccid(self):
        """Get ICCID."""
        try:
            # Try the known working command first
            success, response = self._send_at_command("AT+CRSM=176,12258,0,0,10")
            if success and "+CRSM:" in response:
                # Parse response in format: +CRSM: 144,0,"98410800005897934357"
                match = re.search(r'"(\d{18,20})"', response)
                if match:
                    return match.group(1)
            
            # Fallback to other commands if the first one fails
            commands = [
                "AT$QCCID?",                  # Novatel specific
                "AT+CCID",                    # Standard command
                "AT+ICCID"                    # Alternative command
            ]
            for cmd in commands:
                success, response = self._send_at_command(cmd)
                if success and response:
                    for line in response.split('\n'):
                        line = line.strip()
                        digits = ''.join(filter(str.isdigit, line))
                        if len(digits) >= 18 and len(digits) <= 20:
                            return digits
            return "Unknown"
        except Exception as e:
            self.logger.error(f"Error getting ICCID: {e}")
            return "Unknown"
            
    def _get_phone_number(self):
        """Get phone number from SIM."""
        try:
            success, response = self._send_at_command("AT+CNUM")
            if success and "+CNUM:" in response:
                # Parse response format: +CNUM: "Line 1","+14159716416",145
                match = re.search(r'\+CNUM:.*?"Line 1",\s*"(\+\d+)"', response)
                if match:
                    return match.group(1)  # Return the full number with + prefix
            
            return "Unknown"
        except Exception as e:
            self.logger.error(f"Error getting phone number: {e}")
            return "Unknown"
            
    def cleanup(self):
        """Clean up resources."""
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.is_open = False
            self.initialized = False
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
            
    def _send_at_command(self, command, timeout=None):
        """Send AT command and get response."""
        if not self.is_open:
            self.logger.error("Serial port not open")
            return False, None
            
        if timeout is None:
            timeout = 2.0  # Default timeout
            
        try:
            # Clear buffers
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            
            # Send command
            cmd = command.strip() + "\r\n"
            self.ser.write(cmd.encode())
            
            # Read response
            response = ""
            start_time = time.time()
            
            while True:
                if self.ser.in_waiting:
                    chunk = self.ser.read(self.ser.in_waiting).decode(errors='ignore')
                    response += chunk
                    
                    # Check if response is complete
                    if "OK" in response or "ERROR" in response:
                        break
                        
                # Check timeout
                if time.time() - start_time > timeout:
                    self.logger.warning(f"Command timed out: {command}")
                    break
                    
                time.sleep(0.1)
                
            # Log the response for debugging
            self.logger.debug(f"Command: {command}")
            self.logger.debug(f"Response: {response}")
            
            return "ERROR" not in response, response
            
        except Exception as e:
            self.logger.error(f"Error sending command {command}: {e}")
            return False, None 
            
    def _check_network_registration(self):
        """Check network registration status."""
        try:
            # First check signal quality with CSQ
            success, response = self._send_at_command("AT+CSQ")
            if success and "+CSQ:" in response:
                match = re.search(r'\+CSQ:\s*(\d+),', response)
                if match:
                    rssi = int(match.group(1))
                    if rssi != 99:  # 99 means no signal
                        self.signal_quality = min(100, int((rssi / 31.0) * 100))
                        dbm = -113 + (2 * rssi)
                        self.logger.info(f"Signal strength: {dbm} dBm")
            
            # Check operator info
            success, response = self._send_at_command("AT+COPS?")
            if success and "+COPS:" in response:
                # Parse response format: +COPS: 1,0,"Verizon Wireless",7
                match = re.search(r'\+COPS:\s*\d,\d,"([^"]+)"', response)
                if match:
                    self.operator = match.group(1)
                    self.logger.info(f"Network Operator: {self.operator}")
            
            # Check network attachment
            success, response = self._send_at_command("AT+CGATT?")
            if success and "+CGATT: 1" in response:
                # Check if we have an IP address
                success, ip_response = self._send_at_command("AT+CGPADDR=1")
                if success and "+CGPADDR:" in ip_response:
                    self.logger.info(f"Network Status: Connected with {ip_response.strip()}")
                return "registered"
            
            return "not_registered"
            
        except Exception as e:
            self.logger.error(f"Error checking network registration: {e}")
            return "not_registered"
            
    def initialize_modem(self):
        """Initialize the modem with basic AT commands."""
        try:
            if not self.is_open:
                if not self.open_serial():
                    self.logger.error("Failed to open serial port")
                    return False
            
            # Basic AT test with retries
            for _ in range(3):
                success, response = self._send_at_command("AT")
                if success:
                    break
                time.sleep(1)
                
            if not success:
                self.logger.error("Basic AT test failed")
                return False
            
            # Set modem to known state - using exact working commands
            init_commands = [
                "ATE1V1",        # Enable echo and verbose mode
                "AT+CMEE=2",     # Enable verbose error messages
                "AT+CMGF=1",     # Set SMS text mode (PDU mode by default)
                "AT+CFUN=1",     # Ensure full functionality
                "AT+CPIN?"       # Check SIM status
            ]
            
            for cmd in init_commands:
                success, response = self._send_at_command(cmd)
                if not success:
                    self.logger.warning(f"Command {cmd} failed")
                if cmd == "AT+CPIN?" and "READY" not in response:
                    self.logger.error("SIM card not ready")
                    return False
                time.sleep(0.5)
            
            # Get IMEI using known working command
            success, response = self._send_at_command("AT+CGSN")
            if success and response:
                for line in response.split('\n'):
                    line = line.strip()
                    if len(line) == 15 and line.isdigit():
                        self.imei = line
                        break
            
            if self.imei == "Unknown":
                self.logger.error("Failed to get IMEI")
                return False
            
            # Get ICCID
            self.iccid = self._get_iccid()
            if self.iccid == "Unknown":
                self.logger.warning("Could not get ICCID - continuing anyway")
            
            # Get phone number
            self.phone = self._get_phone_number()
            if self.phone == "Unknown":
                self.logger.warning("Could not get phone number - continuing anyway")
            else:
                self.logger.info(f"Phone Number: {self.phone}")
            
            # Check network registration and operator
            success, response = self._send_at_command("AT+COPS?")
            if success and "+COPS:" in response:
                match = re.search(r'\+COPS: (\d),\d,"([^"]+)",(\d)', response)
                if match:
                    self.operator = match.group(2)
            
            # Get signal quality
            success, response = self._send_at_command("AT+CSQ")
            if success and "+CSQ:" in response:
                match = re.search(r'\+CSQ: (\d+),', response)
                if match:
                    rssi = int(match.group(1))
                    if rssi != 99:  # 99 means no signal
                        self.signal_quality = min(100, int((rssi / 31.0) * 100))
                        # Convert to dBm for logging
                        dbm = -113 + (2 * rssi)
                        self.logger.info(f"Signal strength: {dbm} dBm")
            
            # Check network attachment
            success, response = self._send_at_command("AT+CGATT?")
            if success and "+CGATT: 1" in response:
                self.network_status = "registered"
            else:
                self.network_status = "not_registered"
            
            # Get IP address if connected
            success, response = self._send_at_command("AT+CGPADDR=1")
            if success and "+CGPADDR:" in response:
                match = re.search(r'\+CGPADDR: \d,"([^"]+)"', response)
                if match:
                    self.logger.info(f"IP Address: {match.group(1)}")
            
            self.initialized = True
            self.logger.info(f"Successfully initialized Novatel modem on port {self.port}")
            self.logger.info(f"IMEI: {self.imei}")
            self.logger.info(f"ICCID: {self.iccid}")
            self.logger.info(f"Phone Number: {self.phone}")
            self.logger.info(f"Network Status: {self.network_status}")
            self.logger.info(f"Signal Quality: {self.signal_quality}%")
            self.logger.info(f"Operator: {self.operator}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error during modem initialization: {e}")
            return False 