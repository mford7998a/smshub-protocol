import unittest
from unittest.mock import Mock, patch
from smshub_integration import SmsHubIntegration
import time

class TestSmsHubIntegration(unittest.TestCase):
    def setUp(self):
        self.integration = SmsHubIntegration()

    @patch('requests.post')
    def test_push_sms(self, mock_post):
        """Test SMS pushing to SMS Hub"""
        mock_post.return_value.json.return_value = {'status': 'SUCCESS'}
        
        result = self.integration.push_sms(
            sms_id=123,
            phone=79281234567,
            phone_from='WhatsApp',
            text='Test message'
        )
        
        self.assertTrue(result)
        mock_post.assert_called_once() 

    @patch('requests.post')
    def test_retry_with_delay(self, mock_post):
        """Test retry delay timing"""
        # Mock responses: 2 failures then success
        mock_post.return_value.json.side_effect = [
            {'status': 'ERROR'},
            {'status': 'ERROR'},
            {'status': 'SUCCESS'}
        ]
        
        start_time = time.time()
        
        result = self.integration.push_sms(
            sms_id=123,
            phone=79281234567,
            phone_from='WhatsApp',
            text='Test message'
        )
        
        end_time = time.time()
        
        # Should have waited 20 seconds (2 retries * 10 seconds)
        self.assertGreaterEqual(end_time - start_time, 20)
        self.assertTrue(result)

    def test_response_format(self):
        """Test SMS Hub response format validation"""
        with patch('requests.post') as mock_post:
            # Test various invalid response formats
            invalid_responses = [
                {},  # Empty response
                {'status': 'UNKNOWN'},  # Invalid status
                {'error': 'Some error'},  # Missing status
                None  # No response
            ]
            
            for response in invalid_responses:
                mock_post.return_value.json.return_value = response
                result = self.integration.push_sms(
                    sms_id=123,
                    phone=79281234567,
                    phone_from='WhatsApp',
                    text='Test message'
                )
                self.assertFalse(result) 