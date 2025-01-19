import serial
import time

def send_command(serial_conn, command, expect_response=True):
    """Send AT command and return the response."""
    serial_conn.write((command + '\r').encode())
    time.sleep(0.5)
    if expect_response:
        response = serial_conn.read_all().decode('utf-8', errors='ignore')
        print(f"Command: {command}\nResponse:\n{response}\n")
        return response
    else:
        print(f"Command: {command} sent without waiting for response.")
        return None

def main():
    # Configure the serial connection
    port = 'COM2538'  # Replace with your serial port
    baud_rate = 115200  # Ensure this matches your modem settings

    try:
        # Open serial connection
        ser = serial.Serial(port, baud_rate, timeout=1)
        print(f"Connected to {port} at {baud_rate} baud.\n")

        # List of AT commands to test
        commands = [
            "AT",  # Simple AT query
            "ATE1V1",  # Enable echo and verbose mode
            "AT+CGMM",  # Get model information
            "AT+CGMI",  # Get manufacturer information
            "AT+CGMR",  # Get firmware version
            "AT+CGSN",  # Get IMEI
            "AT+CIMI",  # Get IMSI
            "AT+CCLK?",  # Get clock
            "AT+CPIN?",  # Check SIM PIN status
            "AT+CGDCONT?",  # Show PDP contexts
            "AT+CSQ",  # Signal quality
            "AT+IPR?",  # Serial port speed
            "AT+COPS?",  # Operator selection
            "AT+CREG?",  # Network registration
            "AT+CGACT?",  # Show active PDP contexts
            "AT+CGPADDR=2",  # Get IP address for context 2
            "AT+CGATT?",  # Network attach status
            "AT+CFUN?",  # Device functionality
            "AT+CGCLASS?",  # Station class
            "AT+CSCA?",  # SMS service center
            "AT+CMGF?",  # SMS format mode
            "AT+CMGF=1",  # Set SMS to text mode
            "AT+CMGF?",  # Verify SMS mode
            "AT+CRSM=176,12258,0,0,10",  # Read ICCID
            "AT+CNUM",  # Phone number
        ]

        # Execute each command
        for cmd in commands:
            send_command(ser, cmd)

        # Close the connection
        ser.close()
        print("Testing completed. Connection closed.")

    except serial.SerialException as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
