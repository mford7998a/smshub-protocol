import unittest
from unittest.mock import Mock, patch
from modem_manager import ModemManager
import time

class TestModemManagement(unittest.TestCase):
    def setUp(self):
        """Set up test environment."""
        # Create server with mock SMS Hub
        self.server = Mock()
        self.server.handle_incoming_sms = Mock(return_value=True)
        
        # Create modem manager with short scan interval for testing
        self.modem_manager = ModemManager(server=self.server)
        self.modem_manager.scan_interval = 0.1  # 100ms for testing
        
        # Initialize test modem
        self.modem_manager.modems = {
            'COM1': {
                'status': 'active',
                'phone': '+12025550123',
                'port': 'COM1'
            }
        }

    @patch('serial.tools.list_ports.comports')
    def test_modem_detection(self, mock_comports):
        """Test modem detection"""
        # Mock COM ports
        mock_port = Mock()
        mock_port.device = 'COM1'
        mock_port.description = 'Qualcomm HS-USB'
        mock_port.vid = 0x05C6
        mock_comports.return_value = [mock_port]
        
        self.modem_manager._scan_modems()
        self.assertIn('COM1', self.modem_manager.modems)

    @patch('serial.Serial')
    def test_sms_checking(self, mock_serial):
        """Test SMS checking"""
        # Mock modem response
        mock_instance = Mock()
        mock_instance.read_all.return_value = (
            '+CMGL: 1,"REC UNREAD","+1234567890",,"2024/03/15 12:34:56"\r\n'
            'Test message\r\n'
            'OK\r\n'
        ).encode()
        mock_serial.return_value.__enter__.return_value = mock_instance
        
        messages = self.modem_manager.check_sms('COM1')
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]['text'], 'Test message')

    @patch('serial.Serial')
    def test_sms_immediate_forwarding(self, mock_serial):
        """Test that SMS is forwarded immediately upon receipt"""
        # Mock modem response
        mock_instance = Mock()
        mock_instance.read_all.return_value = (
            '+CMGL: 1,"REC UNREAD","+1234567890",,"2024/03/15 12:34:56"\r\n'
            'Test message\r\n'
            'OK\r\n'
        ).encode()
        mock_serial.return_value.__enter__.return_value = mock_instance
        
        # Run scan loop once with timeout
        self.modem_manager.running = True
        start_time = time.time()
        while time.time() - start_time < 1:  # 1 second timeout
            self.modem_manager._scan_loop()
            if self.server.handle_incoming_sms.call_count > 0:
                break
        self.modem_manager.running = False
        
        # Verify immediate forwarding
        self.server.handle_incoming_sms.assert_called_once_with(
            '+12025550123',  # Phone number from modem info
            '+1234567890',   # Sender from SMS
            'Test message'   # Message text
        )
        
    @patch('serial.Serial')
    def test_sms_deletion_after_processing(self, mock_serial):
        """Test that SMS is deleted after successful processing"""
        # Mock modem response
        mock_instance = Mock()
        mock_instance.read_all.return_value = (
            '+CMGL: 1,"REC UNREAD","+1234567890",,"2024/03/15 12:34:56"\r\n'
            'Test message\r\n'
            'OK\r\n'
        ).encode()
        
        # Track AT commands sent to modem
        sent_commands = []
        def mock_write(cmd):
            sent_commands.append(cmd.decode())
        mock_instance.write = mock_write
        
        mock_serial.return_value.__enter__.return_value = mock_instance
        
        # Process SMS
        messages = self.modem_manager.check_sms('COM1')
        
        # Verify deletion command was sent
        self.assertTrue(any('AT+CMGD=' in cmd for cmd in sent_commands))