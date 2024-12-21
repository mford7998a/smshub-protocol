import unittest
from unittest.mock import patch, MagicMock
from smshub_api import SmsHubAPI, SmsHubConfig
import json
import time

class TestSmsHubAPI(unittest.TestCase):
    def setUp(self):
        """Set up test cases."""
        self.config = SmsHubConfig(
            api_key="test_key",
            agent_id="test_agent",
            server_url="http://test.server",
            api_url="http://test.api"
        )
        self.api = SmsHubAPI(self.config)

    @patch('smshub_api.requests.post')
    def test_push_sms_success(self, mock_post):
        """Test successful SMS push."""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "SUCCESS"}
        mock_post.return_value = mock_response

        result = self.api.push_sms(
            sms_id=12345,
            phone="+79281234567",
            phone_from="TestSender",
            text="Test message"
        )

        self.assertTrue(result)
        
        # Verify request was made with correct data
        call_args = mock_post.call_args
        self.assertIsNotNone(call_args)
        
        _, kwargs = call_args
        request_data = kwargs['json']
        
        # Verify required fields
        self.assertEqual(request_data['action'], 'PUSH_SMS')
        self.assertEqual(request_data['key'], 'test_key')
        self.assertEqual(request_data['smsId'], 12345)
        self.assertEqual(request_data['phone'], 79281234567)  # Should be numeric
        self.assertEqual(request_data['phoneFrom'], 'TestSender')
        self.assertEqual(request_data['text'], 'Test message')

    @patch('smshub_api.requests.post')
    def test_push_sms_retry_success(self, mock_post):
        """Test SMS push with retry succeeding."""
        # First attempt fails, second succeeds
        mock_response1 = MagicMock()
        mock_response1.json.return_value = {"status": "ERROR"}
        
        mock_response2 = MagicMock()
        mock_response2.json.return_value = {"status": "SUCCESS"}
        
        mock_post.side_effect = [mock_response1, mock_response2]

        with patch('time.sleep') as mock_sleep:  # Mock sleep to speed up test
            result = self.api.push_sms(
                sms_id=12345,
                phone="+79281234567",
                phone_from="TestSender",
                text="Test message"
            )

        self.assertTrue(result)
        self.assertEqual(mock_post.call_count, 2)  # Should have tried twice
        mock_sleep.assert_called_once_with(10)  # Should have slept between retries

    def test_push_sms_invalid_phone(self):
        """Test SMS push with invalid phone number."""
        result = self.api.push_sms(
            sms_id=12345,
            phone="invalid-phone",
            phone_from="TestSender",
            text="Test message"
        )
        
        self.assertFalse(result)  # Should fail for invalid phone

    @patch('smshub_api.requests.post')
    def test_push_sms_max_retries(self, mock_post):
        """Test SMS push reaching max retries."""
        # All attempts fail
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "ERROR"}
        mock_post.return_value = mock_response

        with patch('time.sleep') as mock_sleep:  # Mock sleep to speed up test
            result = self.api.push_sms(
                sms_id=12345,
                phone="+79281234567",
                phone_from="TestSender",
                text="Test message"
            )

        self.assertFalse(result)
        self.assertEqual(mock_post.call_count, 30)  # Should have tried max_retries times

if __name__ == '__main__':
    unittest.main()
