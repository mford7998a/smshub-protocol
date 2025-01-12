import logging
from modems.modem_base import ModemBase
import serial
import time
import re

class FranklinT9Modem(ModemBase):
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
        
    def open_serial(self):
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
                time.sleep(1)
            
            self.ser = serial.Serial(
                port=self.port,
                baudrate=115200,
                timeout=2,
                exclusive=True
            )
            self.is_open = True
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
            success, response = self._send_at_command("AT+CGSN")
            if success and response:
                # Extract IMEI from response
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
            success, response = self._send_at_command("AT+CCID")
            if success and response:
                # Extract ICCID from response
                for line in response.split('\n'):
                    line = line.strip()
                    if len(line) >= 18 and len(line) <= 20 and line.isdigit():
                        return line
            return "Unknown"
        except Exception as e:
            self.logger.error(f"Error getting ICCID: {e}")
            return "Unknown"
            
    def _get_phone_number(self):
        """Get phone number from SIM."""
        try:
            success, response = self._send_at_command("AT+CNUM")
            if success and "+CNUM:" in response:
                # Parse response format: +CNUM: "Line 1","+1234567890",145
                match = re.search(r'\+CNUM:.*?"Line 1",\s*"(\+\d+)"', response)
                if match:
                    return match.group(1)  # Return the full number with + prefix
            
            # Try alternative command
            success, response = self._send_at_command("AT+CIMI")
            if success and response:
                for line in response.split('\n'):
                    line = line.strip()
                    if len(line) == 15 and line.isdigit():
                        # Format as phone number with country code
                        return f"+1{line[-10:]}"
            
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
            # Check registration status
            success, response = self._send_at_command("AT+CREG?")
            if not success or "+CREG:" not in response:
                return "not_registered"
            
            # Parse registration status
            parts = response.split(":")[1].strip().split(",")
            if len(parts) >= 2:
                status = int(parts[1])
                # 1 = registered, home network
                # 5 = registered, roaming
                if status in [1, 5]:
                    # Get operator info
                    success, response = self._send_at_command("AT+COPS?")
                    if success and "+COPS:" in response:
                        self.operator = response.split('"')[1] if '"' in response else "Unknown"
                    return "registered" if status == 1 else "roaming"
                elif status == 2:
                    return "searching"
                elif status == 3:
                    return "denied"
            return "not_registered"
            
        except Exception as e:
            self.logger.error(f"Error checking network registration: {e}")
            return "not_registered" 
            
    def initialize_modem(self):
        """Initialize the modem with basic AT commands."""
        try:
            # Open serial port if not already open
            if not self.is_open:
                if not self.open_serial():
                    self.logger.error("Failed to open serial port")
                    return False
            
            # Basic AT test
            success, response = self._send_at_command("AT")
            if not success:
                self.logger.error("Basic AT test failed")
                return False
            
            # Get IMEI
            self.imei = self._get_imei()
            if self.imei == "Unknown":
                self.logger.error("Failed to get IMEI")
                return False
            
            # Get ICCID
            self.iccid = self._get_iccid()
            if self.iccid == "Unknown":
                self.logger.error("Failed to get ICCID")
                return False
            
            # Enable network registration
            success, _ = self._send_at_command("AT+CREG=2")
            if not success:
                self.logger.warning("Failed to enable network registration")
            
            # Check network registration
            self.network_status = self._check_network_registration()
            if self.network_status == "denied":
                self.logger.error("Network registration denied")
                return False
            
            # Get signal quality
            success, response = self._send_at_command("AT+CSQ")
            if success and "+CSQ:" in response:
                parts = response.split(":")[1].strip().split(",")
                if len(parts) >= 1:
                    rssi = int(parts[0])
                    if rssi != 99:  # 99 means no signal
                        self.signal_quality = min(100, int((rssi / 31.0) * 100))
            
            self.initialized = True
            return True
            
        except Exception as e:
            self.logger.error(f"Error during modem initialization: {e}")
            return False 