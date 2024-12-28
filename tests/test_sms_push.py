import unittest
from unittest.mock import Mock, patch
import json
import time
import sys
import os

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smshub_server import SmsHubServer
from smshub_api import SmsHubAPI, SmsHubConfig
from smshub_integration import SmsHubIntegration

class TestSmsPush(unittest.TestCase):
    def setUp(self):
        """Set up test environment before each test."""
        # Initialize server with mock SMS Hub client
        self.server = SmsHubServer()
        
        # Create a proper mock for smshub with response structure
        mock_smshub = Mock()
        mock_response = {'status': 'SUCCESS'}
        mock_smshub.push_sms.return_value = mock_response
        self.server.smshub = mock_smshub
        
        # Create a proper mock for smshub_integration
        mock_integration = Mock()
        mock_integration.push_sms.return_value = True
        self.server.smshub_integration = mock_integration

        # Set up test activation
        self.test_phone = "12025550123"
        self.test_activation_id = int(time.time() * 1000)
        self.server.active_numbers = {
            self.test_phone: {
                'activation_id': self.test_activation_id,
                'service': 'wa',  # WhatsApp service code
                'timestamp': time.time(),
                'sum': 20.00,
                'port': 'COM1'
            }
        }

    def test_push_sms_direct(self):
        """Test direct SMS push to SMSHub integration."""
        with patch('requests.post') as mock_post:
            # Mock successful response
            mock_post.return_value.json.return_value = {'status': 'SUCCESS'}
            mock_post.return_value.status_code = 200
            mock_post.return_value.text = json.dumps({'status': 'SUCCESS'})
            
            # Create integration instance
            integration = SmsHubIntegration()
            
            # Test data
            sms_id = int(time.time() * 1000)
            phone = 12025550123
            phone_from = 'WhatsApp'
            text = 'Test message'
            
            # Call push_sms
            result = integration.push_sms(
                sms_id=sms_id,
                phone=phone,
                phone_from=phone_from,
                text=text
            )
            
            # Verify success
            self.assertTrue(result)
            
            # Verify correct request was made
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            self.assertEqual(call_args[0][0], 'https://agent.unerio.com/agent/api/sms')
            
            # Verify request data
            request_data = call_args[1]['json']
            self.assertEqual(request_data['smsId'], sms_id)
            self.assertEqual(request_data['phone'], phone)
            self.assertEqual(request_data['phoneFrom'], phone_from)
            self.assertEqual(request_data['text'], text)
            self.assertEqual(request_data['action'], 'PUSH_SMS')
            self.assertTrue('key' in request_data)

    def test_handle_incoming_sms(self):
        """Test handling of incoming SMS and forwarding to SMSHub."""
        # Mock successful response from SMS Hub
        mock_response = {'status': 'SUCCESS'}
        self.server.smshub.push_sms.return_value = mock_response
        self.server.smshub_integration.push_sms.return_value = True
        
        # Test incoming SMS
        result = self.server.handle_incoming_sms(
            phone=self.test_phone,
            sender='WhatsApp',
            text='Your WhatsApp code is: 123456'
        )
        
        # Verify success
        self.assertTrue(result)
        
        # Verify SMS Hub client was called
        self.server.smshub.push_sms.assert_called_once()
        
        # Verify call arguments
        call_args = self.server.smshub.push_sms.call_args[1]
        self.assertIsInstance(call_args['sms_id'], int)
        self.assertEqual(call_args['phone'], int(self.test_phone))
        self.assertEqual(call_args['phone_from'], 'wa')  # Should use service code from activation
        self.assertEqual(call_args['text'], 'Your WhatsApp code is: 123456')

if __name__ == '__main__':
    unittest.main() 