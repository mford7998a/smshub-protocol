import sqlite3
import logging
import json
import os
from datetime import datetime
from typing import Dict, Any, List
import time

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ActivationLogger:
    def __init__(self, db_path: str = 'activations.db', log_path: str = 'logs'):
        self.db_path = db_path
        self.log_path = log_path
        self.conn = None  # Store connection for in-memory database
        
        # Ensure log directory exists
        os.makedirs(log_path, exist_ok=True)
        
        # Initialize database
        self._init_db()
        
    def _get_db_connection(self):
        """Get a database connection with proper settings."""
        if self.db_path == ':memory:':
            if self.conn is None:
                self.conn = sqlite3.connect(self.db_path)
                self.conn.row_factory = sqlite3.Row
            return self.conn
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        
    def _init_db(self):
        """Initialize SQLite database and create tables if they don't exist."""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            # Enable foreign keys
            cursor.execute('PRAGMA foreign_keys = ON')
            
            # Create activations table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS activations (
                    activation_id INTEGER PRIMARY KEY,
                    phone_number TEXT NOT NULL,
                    service TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    sum_amount REAL NOT NULL DEFAULT 0.0,
                    currency TEXT NOT NULL DEFAULT 'RUB'
                )
            ''')
            
            # Create events table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS activation_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    activation_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    event_data TEXT,
                    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (activation_id) REFERENCES activations (activation_id)
                )
            ''')
            
            # Create indices for better performance
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_activations_phone 
                ON activations(phone_number)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_events_activation 
                ON activation_events(activation_id)
            ''')
            
            conn.commit()
            logger.info("Database initialized successfully")
            
            if self.db_path != ':memory:':
                conn.close()
                
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise

    def __del__(self):
        """Cleanup database connection on object destruction."""
        if self.conn is not None:
            try:
                self.conn.close()
            except:
                pass

    def log_activation_created(self, activation_id: int, phone: str, service: str, 
                             operator: str, sum_amount: float, currency: str):
        """Log when a new activation is created."""
        timestamp = datetime.now()
        
        # Log to database
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('BEGIN TRANSACTION')
                try:
                    # Insert into activations table
                    cursor.execute('''
                        INSERT INTO activations (
                            activation_id, phone_number, service, operator, 
                            status, created_at, updated_at, sum_amount, currency
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (activation_id, phone, service, operator, 'created', 
                         timestamp, timestamp, sum_amount, currency))
                    
                    # Insert event
                    event_data = {
                        'phone': phone,
                        'service': service,
                        'operator': operator,
                        'sum_amount': sum_amount,
                        'currency': currency
                    }
                    
                    cursor.execute('''
                        INSERT INTO activation_events (
                            activation_id, event_type, event_data, timestamp
                        ) VALUES (?, ?, ?, ?)
                    ''', (activation_id, 'created', json.dumps(event_data), timestamp))
                    
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    raise e
                
        except Exception as e:
            logger.error(f"Error logging activation creation to database: {e}")
            raise
        
        # Log to file
        log_file = os.path.join(self.log_path, f'activation_{activation_id}.log')
        try:
            with open(log_file, 'a') as f:
                log_entry = {
                    'timestamp': timestamp.isoformat(),
                    'event': 'created',
                    'phone': phone,
                    'service': service,
                    'operator': operator,
                    'sum_amount': sum_amount,
                    'currency': currency
                }
                f.write(json.dumps(log_entry) + '\n')
                
        except Exception as e:
            logger.error(f"Error logging activation creation to file: {e}")

    def log_activation_status_update(self, activation_id: int, status: int, additional_data: Dict[str, Any] = None):
        """Log when an activation status is updated."""
        timestamp = datetime.now()
        status_map = {
            1: 'do_not_provide',
            3: 'successfully_sold',
            4: 'cancelled',
            5: 'refunded'
        }
        status_text = status_map.get(status, f'unknown_{status}')
        
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('BEGIN TRANSACTION')
                try:
                    # Check if activation exists
                    cursor.execute('SELECT 1 FROM activations WHERE activation_id = ?', (activation_id,))
                    if not cursor.fetchone():
                        # Create activation record if it doesn't exist
                        cursor.execute('''
                            INSERT INTO activations (
                                activation_id, phone_number, service, operator, 
                                status, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (activation_id, 'unknown', 'unknown', 'unknown', 
                             status_text, timestamp, timestamp))
                    
                    # Update activations table
                    cursor.execute('''
                        UPDATE activations 
                        SET status = ?, updated_at = ?
                        WHERE activation_id = ?
                    ''', (status_text, timestamp, activation_id))
                    
                    # Insert event
                    event_data = {'status': status_text}
                    if additional_data:
                        event_data.update(additional_data)
                        
                    cursor.execute('''
                        INSERT INTO activation_events (
                            activation_id, event_type, event_data, timestamp
                        ) VALUES (?, ?, ?, ?)
                    ''', (activation_id, 'status_update', json.dumps(event_data), timestamp))
                    
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    raise e
                
        except Exception as e:
            logger.error(f"Error logging activation status update to database: {e}")
            raise
        
        # Log to file
        log_file = os.path.join(self.log_path, f'activation_{activation_id}.log')
        try:
            with open(log_file, 'a') as f:
                log_entry = {
                    'timestamp': timestamp.isoformat(),
                    'event': 'status_update',
                    'status': status_text,
                    'additional_data': additional_data
                }
                f.write(json.dumps(log_entry) + '\n')
                
        except Exception as e:
            logger.error(f"Error logging activation status update to file: {e}")

    def log_sms_received(self, activation_id: int, sms_text: str, sender: str):
        """Log when an SMS is received for an activation."""
        timestamp = datetime.now()
        
        # Log to database
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Insert event
                event_data = {
                    'sms_text': sms_text,
                    'sender': sender
                }
                
                cursor.execute('''
                    INSERT INTO activation_events (
                        activation_id, event_type, event_data, timestamp
                    ) VALUES (?, ?, ?, ?)
                ''', (activation_id, 'sms_received', json.dumps(event_data), timestamp))
                
                conn.commit()
                
        except Exception as e:
            logger.error(f"Error logging SMS receipt to database: {e}")
            
        # Log to file
        log_file = os.path.join(self.log_path, f'activation_{activation_id}.log')
        try:
            with open(log_file, 'a') as f:
                log_entry = {
                    'timestamp': timestamp.isoformat(),
                    'event': 'sms_received',
                    'sms_text': sms_text,
                    'sender': sender
                }
                f.write(json.dumps(log_entry) + '\n')
                
        except Exception as e:
            logger.error(f"Error logging SMS receipt to file: {e}")

    def log_sms_delivered(self, activation_id: int, text: str, recipient: str = None, delivery_status: str = None):
        """Log when an SMS is successfully delivered to SMS Hub."""
        timestamp = datetime.now()
        
        # Log to database
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Insert event
                event_data = {
                    'text': text,
                    'recipient': recipient,
                    'delivery_status': delivery_status,
                    'delivery_time': timestamp.isoformat()
                }
                
                cursor.execute('''
                    INSERT INTO activation_events (
                        activation_id, event_type, event_data, timestamp
                    ) VALUES (?, ?, ?, ?)
                ''', (activation_id, 'sms_delivered', json.dumps(event_data), timestamp))
                
                conn.commit()
                
        except Exception as e:
            logger.error(f"Error logging SMS delivery to database: {e}")
            
        # Log to file
        log_file = os.path.join(self.log_path, f'activation_{activation_id}.log')
        try:
            with open(log_file, 'a') as f:
                log_entry = {
                    'timestamp': timestamp.isoformat(),
                    'event': 'sms_delivered',
                    'text': text,
                    'recipient': recipient,
                    'delivery_status': delivery_status
                }
                f.write(json.dumps(log_entry) + '\n')
                
        except Exception as e:
            logger.error(f"Error logging SMS delivery to file: {e}")

    def get_activation_history(self, activation_id: int) -> Dict[str, Any]:
        """Get complete history of an activation from both database and log file."""
        result = {
            'activation_info': None,
            'events': [],
            'log_file_entries': []
        }
        
        # Get from database
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Get activation info
                cursor.execute('''
                    SELECT * FROM activations WHERE activation_id = ?
                ''', (activation_id,))
                row = cursor.fetchone()
                if row:
                    result['activation_info'] = dict(row)
                
                # Get events
                cursor.execute('''
                    SELECT * FROM activation_events 
                    WHERE activation_id = ?
                    ORDER BY timestamp
                ''', (activation_id,))
                result['events'] = [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"Error retrieving activation history from database: {e}")
            raise
        
        # Get from log file
        log_file = os.path.join(self.log_path, f'activation_{activation_id}.log')
        try:
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    result['log_file_entries'] = [json.loads(line) for line in f]
        except Exception as e:
            logger.error(f"Error retrieving activation history from log file: {e}")
        
        return result

    def search_activations(self, **kwargs) -> List[Dict[str, Any]]:
        """Search activations based on various criteria."""
        query = "SELECT * FROM activations WHERE 1=1"
        params = []
        
        for key, value in kwargs.items():
            if value is not None:
                query += f" AND {key} = ?"
                params.append(value)
                
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error searching activations: {e}")
            return [] 

    def get_earnings_by_timeframe(self, timeframe='all'):
        """Calculate earnings for different timeframes"""
        now = datetime.now()
        query = "SELECT SUM(sum_amount) FROM activations WHERE status = 'successfully_sold'"
        
        if timeframe == 'day':
            query += " AND date(created_at) = date('now')"
        elif timeframe == 'week':
            query += " AND created_at >= datetime('now', '-7 days')"
        elif timeframe == 'month':
            query += " AND created_at >= datetime('now', '-30 days')"
        elif timeframe == 'year':
            query += " AND created_at >= datetime('now', '-365 days')"
        
        with self._get_db_connection() as conn:
            result = conn.execute(query).fetchone()[0]
            return result or 0.0

    def get_earnings_by_service(self):
        """Calculate total earnings per service"""
        query = """
        SELECT service, SUM(sum_amount) as total
        FROM activations 
        WHERE status = 'successfully_sold'
        GROUP BY service
        """
        with self._get_db_connection() as conn:
            return dict(conn.execute(query).fetchall())

    def get_earnings_by_phone(self):
        """Calculate total earnings per phone number"""
        query = """
        SELECT phone_number, SUM(sum_amount) as total
        FROM activations 
        WHERE status = 'successfully_sold'
        GROUP BY phone_number
        """
        with self._get_db_connection() as conn:
            return dict(conn.execute(query).fetchall())

    def get_activations_by_phone(self, phone_number):
        """Get total activations and earnings for a specific phone number"""
        query = """
        SELECT 
            COUNT(*) as total_activations, 
            SUM(sum_amount) as total_earnings,
            SUM(CASE WHEN date(created_at) = date('now') THEN sum_amount ELSE 0 END) as today_earnings
        FROM activations 
        WHERE phone_number = ? AND status = 'successfully_sold'
        """
        with self._get_db_connection() as conn:
            result = conn.execute(query, (phone_number,)).fetchone()
            return {
                'total_activations': result[0] or 0,
                'total_earnings': result[1] or 0.0,
                'today_earnings': result[2] or 0.0
            } 