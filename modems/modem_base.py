from abc import ABC, abstractmethod

class ModemBase(ABC):
    """Base class for all modem implementations."""
    
    def __init__(self, port):
        self.port = port
    
    @abstractmethod
    def open_serial(self):
        """Open the serial connection to the modem."""
        pass
        
    @abstractmethod
    def close_serial(self):
        """Close the serial connection."""
        pass
        
    @abstractmethod
    def _get_imei(self):
        """Get the modem's IMEI number."""
        pass
        
    @abstractmethod
    def _get_iccid(self):
        """Get the SIM card's ICCID."""
        pass
        
    @abstractmethod
    def _check_network_registration(self):
        """Check the network registration status."""
        pass
        
    @abstractmethod
    def initialize_modem(self):
        """Initialize the modem and prepare it for use."""
        pass
        
    @abstractmethod
    def _send_at_command(self, command, timeout=None):
        """Send an AT command to the modem and get the response."""
        pass
        
    def cleanup(self):
        """Clean up resources."""
        self.close_serial() 