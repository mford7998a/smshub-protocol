import unittest
from unittest.mock import Mock, patch
import time
from smshub_server import SmsHubServer
from modem_manager import ModemManager
from activation_logger import ActivationLogger

class TestActivationFlow(unittest.TestCase):
    def setUp(self):
        """Set up test environment before each test."""
        # Initialize database first with in-memory SQLite
        self.activation_logger = ActivationLogger(db_path=':memory:')
        
        # Initialize server with required services
        self.server = SmsHubServer()
        
        # Mock SMS Hub client
        mock_smshub = Mock()
        mock_smshub.forward_sms = Mock(return_value={'status': 'SUCCESS'})
        mock_smshub.push_sms = Mock(return_value={'status': 'SUCCESS'})
        self.server.smshub = mock_smshub
        
        self.server.services = {
            'whatsapp': True,
            'telegram': True,
            'uber': True,
            'facebook': True,
            'instagram': True,
            'twitter': True,
            'gmail': True,
            'amazon': True,
            'netflix': True,
            'spotify': True,
            'tinder': True
        }
        
        # Set up Flask test client
        self.app = self.server.app
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        
        # Set up modem manager with server reference
        self.modem_manager = ModemManager(server=self.server)
        
        # Link components
        self.server.activation_logger = self.activation_logger
        self.server.modem_manager = self.modem_manager
        
        # Initialize test data with US phone numbers
        self.server.modems = {
            '+12025550123': {
                'status': 'active',
                'phone': '+12025550123',
                'port': 'COM1'
            }
        }
        
        self.server.active_numbers = {}
        
    def tearDown(self):
        """Clean up after each test."""
        self.ctx.pop()
        self.server.modems.clear()
        self.server.active_numbers.clear()

    def test_1_get_number_request(self):
        """Test GET_NUMBER request handling"""
        test_data = {
            'country': 'usa',
            'operator': 'any',
            'service': 'whatsapp',
            'sum': 20.00,
            'action': 'GET_NUMBER',
            'currency': 840,  # USD currency code
            'key': '1234'
        }
        
        # Mock an available modem
        self.server.modems = {
            '+12025550123': {  # US format number
                'status': 'active',
                'phone': '+12025550123'
            }
        }
        
        response = self.server.handle_get_number(test_data)
        self.assertEqual(response.json['status'], 'SUCCESS')
        self.assertTrue('number' in response.json)
        self.assertTrue('activationId' in response.json)

    def test_2_sms_reception(self):
        """Test SMS reception and forwarding"""
        # First create an activation
        test_data = {
            'country': 'usa',
            'operator': 'any',
            'service': 'whatsapp',
            'sum': 20.00,
            'action': 'GET_NUMBER',
            'currency': 840,
            'key': '1234'
        }
        
        # Set up test modem
        self.server.modems = {
            '+12025550123': {
                'status': 'active',
                'phone': '+12025550123',
                'port': 'COM1'
            }
        }
        
        # Get number and create activation
        response = self.server.handle_get_number(test_data)
        self.assertEqual(response.json['status'], 'SUCCESS')
        activation_id = response.json['activationId']
        
        # Mock SMS reception
        test_sms = {
            'sender': 'WhatsApp',
            'text': 'Your code is 123456',
            'port': 'COM1'
        }
        
        # Mock modem info
        self.modem_manager.modems = {
            'COM1': {
                'phone': '+12025550123',
                'status': 'active'
            }
        }
        
        # Test SMS handling
        result = self.modem_manager.handle_sms_received(
            port=test_sms['port'],
            sender=test_sms['sender'],
            text=test_sms['text']
        )
        self.assertTrue(result)
        
        # Verify SMS Hub client was called
        self.server.smshub.push_sms.assert_called_once()

    def test_3_sms_forwarding(self):
        """Test SMS forwarding to SMS Hub"""
        # First create an activation
        test_data = {
            'country': 'usa',
            'operator': 'any',
            'service': 'whatsapp',
            'sum': 20.00,
            'action': 'GET_NUMBER',
            'currency': 840,
            'key': '1234'
        }
        
        # Set up test modem
        self.server.modems = {
            '+12025550123': {
                'status': 'active',
                'phone': '+12025550123'
            }
        }
        
        # Get number and create activation
        response = self.server.handle_get_number(test_data)
        self.assertEqual(response.json['status'], 'SUCCESS')
        activation_id = response.json['activationId']
        
        # Test SMS forwarding
        result = self.server.handle_incoming_sms(
            phone='+12025550123',
            sender='WhatsApp',
            text='Your code is 123456'
        )
        self.assertTrue(result)
        
        # Verify SMS Hub client was called
        self.server.smshub.push_sms.assert_called_once()

    def test_4_finish_activation(self):
        """Test FINISH_ACTIVATION handling"""
        # First create an activation
        test_data = {
            'country': 'usa',
            'operator': 'any',
            'service': 'whatsapp',
            'sum': 20.00,
            'action': 'GET_NUMBER',
            'currency': 840,
            'key': '1234'
        }
        
        # Set up test modem
        self.server.modems = {
            '+12025550123': {
                'status': 'active',
                'phone': '+12025550123'
            }
        }
        
        # Get number and create activation
        response = self.server.handle_get_number(test_data)
        self.assertEqual(response.json['status'], 'SUCCESS')
        activation_id = response.json['activationId']
        
        # Now test finish activation
        finish_data = {
            'action': 'FINISH_ACTIVATION',
            'key': '1234',
            'activationId': activation_id,
            'status': 3  # Successfully completed
        }
        
        response = self.server.handle_finish_activation(finish_data)
        self.assertEqual(response.json['status'], 'SUCCESS')

    def test_5_retry_logic(self):
        """Test SMS forwarding retry logic"""
        # First create an activation
        test_data = {
            'country': 'usa',
            'operator': 'any',
            'service': 'whatsapp',
            'sum': 20.00,
            'action': 'GET_NUMBER',
            'currency': 840,
            'key': '1234'
        }
        
        # Set up test modem
        self.server.modems = {
            '+12025550123': {
                'status': 'active',
                'phone': '+12025550123'
            }
        }
        
        # Get number and create activation
        response = self.server.handle_get_number(test_data)
        self.assertEqual(response.json['status'], 'SUCCESS')
        activation_id = response.json['activationId']
        
        with patch('requests.post') as mock_post:
            # Mock failed response then success
            mock_post.return_value.json.side_effect = [
                {'status': 'ERROR'},
                {'status': 'ERROR'},
                {'status': 'SUCCESS'}
            ]
            
            result = self.server.handle_incoming_sms(
                phone='+12025550123',
                sender='WhatsApp',
                text='Your code is 123456'
            )
            
            self.assertTrue(result)
            self.assertEqual(mock_post.call_count, 3)

    def test_6_database_logging(self):
        """Test activation logging"""
        # Test activation creation with US number
        self.activation_logger.log_activation_created(
            activation_id=123,
            phone='+12025550123',
            service='whatsapp',
            operator='any',
            sum_amount=20.00,
            currency='USD'
        )
        
        # Test status update
        self.activation_logger.log_activation_status_update(
            activation_id=123,
            status=3,  # Successfully completed
            additional_data={'completion_time': 300}
        )
        
        # Verify records
        history = self.activation_logger.get_activation_history(123)
        self.assertIsNotNone(history['activation_info'])
        self.assertEqual(len(history['events']), 2)

    def test_7_idempotent_finish_activation(self):
        """Test that finishing same activation twice works correctly"""
        # First create an activation
        test_data = {
            'country': 'usa',
            'operator': 'any',
            'service': 'whatsapp',
            'sum': 20.00,
            'action': 'GET_NUMBER',
            'currency': 840,
            'key': '1234'
        }
        
        # Set up test modem
        self.server.modems = {
            '+12025550123': {
                'status': 'active',
                'phone': '+12025550123'
            }
        }
        
        # Get number and create activation
        response = self.server.handle_get_number(test_data)
        self.assertEqual(response.json['status'], 'SUCCESS')
        activation_id = response.json['activationId']
        
        # Test data for finish activation
        finish_data = {
            'action': 'FINISH_ACTIVATION',
            'key': '1234',
            'activationId': activation_id,
            'status': 3
        }
        
        # First finish attempt
        response1 = self.server.handle_finish_activation(finish_data)
        self.assertEqual(response1.json['status'], 'SUCCESS')
        
        # Second finish attempt should also succeed
        response2 = self.server.handle_finish_activation(finish_data)
        self.assertEqual(response2.json['status'], 'SUCCESS')

    def test_8_exception_phone_set(self):
        """Test handling of excluded phone numbers"""
        test_data = {
            'country': 'usa',
            'operator': 'any',
            'service': 'whatsapp',
            'sum': 20.00,
            'action': 'GET_NUMBER',
            'currency': 840,  # USD currency code
            'key': '1234',
            'exceptionPhoneSet': ['1202', '1301']  # DC and Maryland area codes
        }
        
        # Mock modems with excluded and allowed numbers
        self.server.modems = {
            '+12025550123': {'status': 'active', 'phone': '+12025550123'},  # Should be excluded (DC)
            '+13015550123': {'status': 'active', 'phone': '+13015550123'},  # Should be excluded (MD)
            '+12125550123': {'status': 'active', 'phone': '+12125550123'}   # Should be allowed (NY)
        }
        
        response = self.server.handle_get_number(test_data)
        self.assertEqual(response.json['status'], 'SUCCESS')
        self.assertTrue(response.json['number'].startswith('1212'))  # NY area code

    def test_9_numeric_field_validation(self):
        """Test numeric field type validation"""
        test_data = {
            'action': 'PUSH_SMS',
            'key': '1234',
            'smsId': '123',  # Should be numeric
            'phone': '79261234567',  # Should be numeric
            'phoneFrom': 'WhatsApp',
            'text': 'Test message'
        }
        
        response = self.server.handle_push_sms(test_data)
        self.assertEqual(response.json['status'], 'ERROR')
        self.assertIn('Invalid field types', response.json['error']) 