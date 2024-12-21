import tkinter as tk
from modem_manager import ModemManager
from smshub_server import SmsHubServer
from smshub_integration import SmsHubIntegration
from gui import ModemGUI
from config import config
import logging
import threading
import time

# Configure logging to write to a file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("activation_log.txt"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)  # Add logger definition

def main():
    try:
        logger.info("Starting SMS Hub Agent application...")
        
        # Initialize SMS Hub integration first
        logger.info("Initializing SMS Hub integration...")
        smshub = SmsHubIntegration()
        
        # Initialize server with SMS Hub integration
        logger.info("Starting SMS Hub Agent server...")
        server = SmsHubServer()
        server.host = "0.0.0.0"  # Listen on all interfaces
        server.port = config.get('server_port', 5000)  # Get port from config or use default 5000
        server.smshub = smshub  # Link SMS Hub to server
        
        # Start server in a separate thread
        server_thread = threading.Thread(target=server.run, daemon=True)
        server_thread.start()
        logger.info(f"Server started on http://{server.host}:{server.port}")
        
        # Give the server a moment to start
        time.sleep(1)
        
        # Initialize modem manager with server reference
        logger.info("Initializing modem manager...")
        modem_manager = ModemManager(server=server)
        
        # Create GUI first so it's ready to show updates
        logger.info("Starting GUI...")
        app = ModemGUI(modem_manager, server)
        
        # Start modem scanning after GUI is ready
        logger.info("Starting modem scanning...")
        modem_manager.start()  # This will trigger automatic registration of any found modems
        
        # Run the GUI main loop
        app.run()
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Application terminated by user")
    except Exception as e:
        logger.error(f"Application error: {e}")
        raise 