import logging
import sys
import time
from modems.novatel_551l import Novatel551LModem

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

def test_modem():
    try:
        # First try to find the modem port
        print("\nSearching for Novatel modem...")
        port = Novatel551LModem.find_modem_port()
        
        if not port:
            print("❌ Could not find Novatel modem port")
            return False
            
        print(f"✓ Found Novatel modem on port: {port}")
        
        # Create modem instance
        print("\nInitializing modem...")
        modem = Novatel551LModem(port)
        
        # Try to initialize
        if not modem.initialize_modem():
            print("❌ Failed to initialize modem")
            return False
            
        print("\nModem Information:")
        print(f"Port: {modem.port}")
        print(f"IMEI: {modem.imei}")
        print(f"ICCID: {modem.iccid}")
        print(f"Network Status: {modem.network_status}")
        print(f"Signal Quality: {modem.signal_quality}%")
        print(f"Operator: {modem.operator}")
        
        # Test some basic AT commands
        print("\nTesting basic AT commands...")
        commands = [
            "AT+CGMI",                    # Manufacturer
            "AT+CGMM",                    # Model
            "AT+CGMR",                    # Firmware version
            "AT+CRSM=176,12258,0,0,10",  # ICCID
            "AT+CREG?",                   # Network registration
            "AT+COPS?",                   # Current operator
            "AT+CSQ",                     # Signal quality
            "AT+CPIN?",                   # SIM status
            "AT+CNUM"                    # Phone number
        ]
        
        for cmd in commands:
            success, response = modem._send_at_command(cmd)
            print(f"\nCommand: {cmd}")
            print(f"Success: {'✓' if success else '❌'}")
            print(f"Response: {response.strip() if response else 'No response'}")
            time.sleep(0.5)
        
        # Clean up
        print("\nCleaning up...")
        modem.cleanup()
        print("✓ Test completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Error during test: {e}")
        return False

if __name__ == "__main__":
    print("=== Novatel 551L Modem Test ===")
    test_modem() 