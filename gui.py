import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import queue
import time
import logging
from smshub_integration import SmsHubIntegration
from config import SMSHUB_API_KEY, config
from datetime import datetime

logger = logging.getLogger(__name__)

class ModemGUI(ttk.Frame):
    def __init__(self, modem_manager, server):
        """Initialize the GUI."""
        self.root = tk.Tk()
        super().__init__(self.root)
        self.root.title("SMS Hub Agent")
        self.root.geometry("1300x900")  # Set a reasonable default size
        
        # Configure root window to be resizable
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        # Initialize managers
        self.modem_manager = modem_manager
        self.server = server
        self.smshub = server.smshub
        
        # Initialize state variables
        self.selected_port = None
        self.connected = False
        self.update_queue = queue.Queue()
        self.log_queue = queue.Queue()
        self.message_history = {}  # Store message history for each modem
        
        # Create main container
        self.main_container = ttk.Frame(self.root)
        self.main_container.grid(row=0, column=0, sticky="nsew")
        self.main_container.grid_rowconfigure(0, weight=1)
        self.main_container.grid_columnconfigure(0, weight=1)
        
        # Create notebook
        self.notebook = ttk.Notebook(self.main_container)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        # Create tabs
        self.device_tab = ttk.Frame(self.notebook)
        self.server_tab = ttk.Frame(self.notebook)
        self.messages_tab = ttk.Frame(self.notebook)
        self.console_tab = ttk.Frame(self.notebook)  # New console tab
        self.earnings_tab = ttk.Frame(self.notebook)  # New earnings tab
        
        # Configure tab frames to be resizable
        for tab in (self.device_tab, self.server_tab, self.messages_tab, self.console_tab, self.earnings_tab):
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)
        
        self.notebook.add(self.device_tab, text="Device Management")
        self.notebook.add(self.server_tab, text="SMS Hub Dashboard")
        self.notebook.add(self.messages_tab, text="Message History")
        self.notebook.add(self.console_tab, text="Console Output")
        self.notebook.add(self.earnings_tab, text="Earnings")
        
        # Create tab contents
        self.create_device_tab()
        self.create_server_tab()
        self.create_messages_tab()
        self.create_console_tab()  # New method for console tab
        self.create_earnings_tab()  # New method for earnings tab
        
        # Start update thread
        self.start_update_thread()
        
        # Start console logging
        self.setup_console_logging()

    def create_device_tab(self):
        """Create the device management tab."""
        # Device List Frame with proper weights
        list_frame = ttk.LabelFrame(self.device_tab, text="Connected Devices", padding="5")
        list_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        list_frame.grid_rowconfigure(0, weight=1)  # Make the tree expand vertically
        list_frame.grid_columnconfigure(0, weight=1)  # Make the tree expand horizontally
        
        # Create Treeview for devices with scrollbars
        tree_frame = ttk.Frame(list_frame)
        tree_frame.grid(row=0, column=0, sticky="nsew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        # Create Treeview with all columns
        columns = (
            "port", "status", "iccid", "network", "phone", "carrier", 
            "signal", "type", "last_seen", "total_activations", 
            "total_earnings", "today_earnings"
        )
        self.devices_tree = ttk.Treeview(tree_frame, columns=columns, show='headings')
        
        # Define column headings and widths
        headings = {
            'port': ('Port', 100),
            'status': ('Status', 80),
            'iccid': ('ICCID', 150),
            'network': ('Network', 100),
            'phone': ('Phone', 120),
            'carrier': ('Carrier', 120),
            'signal': ('Signal', 60),
            'type': ('Type', 100),
            'last_seen': ('Last Seen', 150),
            'total_activations': ('Activations', 100),
            'total_earnings': ('Total Earnings', 100),
            'today_earnings': ("Today's Earnings", 100)
        }
        
        for col, (heading, width) in headings.items():
            self.devices_tree.heading(col, text=heading)
            self.devices_tree.column(col, width=width, anchor='center')
        
        # Add scrollbars
        y_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.devices_tree.yview)
        x_scrollbar = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.devices_tree.xview)
        self.devices_tree.configure(yscrollcommand=y_scrollbar.set, xscrollcommand=x_scrollbar.set)
        
        # Grid layout for treeview and scrollbars
        self.devices_tree.grid(row=0, column=0, sticky="nsew")
        y_scrollbar.grid(row=0, column=1, sticky="ns")
        x_scrollbar.grid(row=1, column=0, sticky="ew")
        
        self.devices_tree.bind('<<TreeviewSelect>>', self.on_select)
        
        # Control Frame
        control_frame = ttk.Frame(self.device_tab)
        control_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        
        # Status Label
        self.selected_label = ttk.Label(control_frame, text="No device selected")
        self.selected_label.pack(side="left", padx=5)
        
        # Control Buttons
        self.connect_button = ttk.Button(control_frame, text="Connect All", command=self.toggle_connections)
        self.connect_button.pack(side="right", padx=5)
        
        ttk.Button(control_frame, text="Scan", command=self.scan_devices).pack(side="right", padx=5)

    def create_console_tab(self):
        """Create the console output tab."""
        # Create main frame
        console_frame = ttk.Frame(self.console_tab)
        console_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        console_frame.grid_rowconfigure(0, weight=1)
        console_frame.grid_columnconfigure(0, weight=1)
        
        # Create Text widget
        self.console_text = scrolledtext.ScrolledText(console_frame, wrap=tk.WORD)
        self.console_text.grid(row=0, column=0, sticky="nsew")
        self.console_text.configure(state='disabled')
        
        # Create button frame
        button_frame = ttk.Frame(console_frame)
        button_frame.grid(row=1, column=0, sticky="ew", pady=5)
        
        # Add clear button
        ttk.Button(button_frame, text="Clear Console", 
                  command=self.clear_console).pack(side="right", padx=5)
        
        # Add auto-scroll checkbox
        self.auto_scroll = tk.BooleanVar(value=True)
        ttk.Checkbutton(button_frame, text="Auto-scroll", 
                       variable=self.auto_scroll).pack(side="right", padx=5)

    def clear_console(self):
        """Clear the console output."""
        self.console_text.configure(state='normal')
        self.console_text.delete(1.0, tk.END)
        self.console_text.configure(state='disabled')

    def setup_console_logging(self):
        """Setup logging to console widget."""
        class QueueHandler(logging.Handler):
            def __init__(self, queue):
                super().__init__()
                self.queue = queue

            def emit(self, record):
                self.queue.put(record)

        # Create queue handler and set formatter
        queue_handler = QueueHandler(self.log_queue)
        queue_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        
        # Add handler to root logger
        logging.getLogger().addHandler(queue_handler)
        
        # Start checking queue
        self.check_log_queue()

    def check_log_queue(self):
        """Check for new log records."""
        while True:
            try:
                record = self.log_queue.get_nowait()
                self.update_console(record)
            except queue.Empty:
                break
        self.root.after(100, self.check_log_queue)

    def update_console(self, record):
        """Update console with new log record."""
        msg = self.format_log_message(record)
        self.console_text.configure(state='normal')
        self.console_text.insert(tk.END, msg + '\n')
        if self.auto_scroll.get():
            self.console_text.see(tk.END)
        self.console_text.configure(state='disabled')

    def format_log_message(self, record):
        """Format log record for display."""
        # Color codes for different log levels
        colors = {
            'ERROR': '#FF0000',
            'WARNING': '#FFA500',
            'INFO': '#000000',
            'DEBUG': '#808080'
        }
        
        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
        
        # Format message based on level
        return f"[{timestamp}] {record.levelname}: {record.getMessage()}"

    def create_server_tab(self):
        """Create the SMS Hub server configuration tab."""
        # Connection Information Frame
        conn_frame = ttk.LabelFrame(self.server_tab, text="Connection Information", padding="5")
        conn_frame.pack(fill="x", padx=5, pady=5)
        
        # Local API Endpoint
        local_frame = ttk.Frame(conn_frame)
        local_frame.pack(fill="x", padx=5)
        ttk.Label(local_frame, text="Local API Endpoint:").pack(side="left", padx=5)
        self.local_url = ttk.Label(local_frame, text="http://0.0.0.0:5000")
        self.local_url.pack(side="left", padx=5)
        
        # Public API Endpoint
        public_frame = ttk.Frame(conn_frame)
        public_frame.pack(fill="x", padx=5)
        ttk.Label(public_frame, text="Public API Endpoint:").pack(side="left", padx=5)
        self.tunnel_url = ttk.Label(public_frame, text="Waiting for connection...", foreground='red')
        self.tunnel_url.pack(side="left", padx=5)

        # System Configuration Frame
        config_frame = ttk.LabelFrame(self.server_tab, text="System Configuration", padding="5")
        config_frame.pack(fill="x", padx=5, pady=5)
        
        # Debug Mode Toggle
        debug_var_frame = ttk.Frame(config_frame)
        debug_var_frame.pack(side="left", padx=5)
        self.debug_var = tk.BooleanVar(value=config.get('debug_mode', False))
        debug_check = ttk.Checkbutton(
            debug_var_frame,
            text="Enable Debug Logging (requires restart)",
            variable=self.debug_var,
            command=self.toggle_debug_mode
        )
        debug_check.pack(side="left", padx=5)

        # Scan Interval Setting
        scan_frame = ttk.Frame(config_frame)
        scan_frame.pack(side="left", padx=20)
        
        ttk.Label(scan_frame, text="Update Interval (seconds):").pack(side="left", padx=5)
        self.scan_var = tk.StringVar(value=str(config.get('scan_interval', 10)))
        scan_entry = ttk.Entry(scan_frame, textvariable=self.scan_var, width=5)
        scan_entry.pack(side="left", padx=5)
        
        ttk.Button(scan_frame, text="Apply", command=self.update_scan_interval).pack(side="left", padx=5)

        # Service Statistics Frame
        services_frame = ttk.LabelFrame(self.server_tab, text="Service Statistics", padding="5")
        services_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Create Treeview for services
        columns = ('service', 'quantity', 'active', 'completed')
        self.services_tree = ttk.Treeview(services_frame, columns=columns, show='headings', height=20)
        
        # Define column headings and widths
        headings = {
            'service': ('Service Name', 200),
            'quantity': ('Available Numbers', 120),
            'active': ('Active Rentals', 100),
            'completed': ('Completed', 100)
        }
        
        for col, (heading, width) in headings.items():
            self.services_tree.heading(col, text=heading)
            self.services_tree.column(col, width=width, anchor='center')

        # Add scrollbar for services
        services_scroll = ttk.Scrollbar(services_frame, orient="vertical", command=self.services_tree.yview)
        self.services_tree.configure(yscrollcommand=services_scroll.set)
        
        self.services_tree.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        services_scroll.pack(side="right", fill="y")

    def on_select(self, event):
        """Handle device selection."""
        selection = self.devices_tree.selection()
        if selection:
            item = self.devices_tree.item(selection[0])
            new_port = item['values'][0]  # Port is at index 0 now
            
            # Only update if selection actually changed
            if new_port != self.selected_port:
                self.selected_port = new_port
                self.selected_label.config(text=f"Selected: {self.selected_port}")
                self.refresh_messages()
        else:
            self.selected_port = None
            self.selected_label.config(text="No device selected")
            self.clear_messages()

    def clear_messages(self):
        """Clear the message list."""
        for item in self.msg_tree.get_children():
            self.msg_tree.delete(item)

    def refresh_messages(self):
        """Refresh messages for selected device."""
        if not self.selected_port:
            return

        messages = self.modem_manager.check_sms(self.selected_port)
        
        # Store current scroll position
        try:
            scroll_pos = self.msg_tree.yview()
        except:
            scroll_pos = (0, 0)

        self.clear_messages()
        
        # Update messages
        for msg in messages:
            self.msg_tree.insert('', 'end', values=(
                msg['index'],
                msg['status'],
                msg['sender'],
                msg['timestamp'],
                msg['text']
            ))

        # Restore scroll position
        try:
            self.msg_tree.yview_moveto(scroll_pos[0])
        except:
            pass 

    def toggle_connections(self):
        """Connect or disconnect all devices."""
        try:
            if not self.connected:
                self.modem_manager.connect_all()
                self.connected = True
                self.connect_button.config(text="Disconnect All")
                self.selected_label.config(text="Connecting to all devices...")
            else:
                self.modem_manager.disconnect_all()
                self.connected = False
                self.connect_button.config(text="Connect All")
                self.selected_label.config(text="Disconnecting all devices...")
            
            # Give devices time to connect/disconnect
            self.root.after(1000, self.update_device_info)
        except Exception as e:
            logger.error(f"Error toggling connections: {e}")
            self.selected_label.config(text=f"Error toggling connections: {e}")

    def scan_devices(self):
        """Scan for new devices."""
        try:
            self.modem_manager._scan_modems()
            self.selected_label.config(text="Device scan complete")
            self.update_device_info()
        except Exception as e:
            logger.error(f"Error scanning devices: {e}")
            self.selected_label.config(text=f"Error scanning devices: {e}")

    def clear_device_info(self):
        """Clear the device information display."""
        for item in self.device_tree.get_children():
            self.device_tree.delete(item)

    def send_command(self):
        """Send AT command to selected device."""
        if not self.selected_port:
            self.selected_label.config(text="Please select a device first")
            return

        command = self.cmd_entry.get()
        if command:
            response = self.modem_manager.send_at_command(self.selected_port, command)
            self.selected_label.config(text=f"Response: {response}")
            self.cmd_entry.delete(0, tk.END)
            # Update device info after command
            self.update_device_info()

    def update_tunnel_status(self):
        """Update tunnel status display."""
        url = self.tunnel_manager.get_public_url()
        if url:
            self.tunnel_url_label.config(text=url, foreground='green')
        else:
            self.tunnel_url_label.config(text="Not Connected", foreground='red')

    def toggle_debug_mode(self):
        """Toggle debug mode in config."""
        debug_mode = self.debug_var.get()
        config.set('debug_mode', debug_mode)
        messagebox.showinfo(
            "Debug Mode Changed",
            f"Debug mode {'enabled' if debug_mode else 'disabled'}. Please restart the application for changes to take effect."
        )

    def update_scan_interval(self):
        """Update modem scan interval."""
        try:
            interval = int(self.scan_var.get())
            if interval < 5:
                messagebox.showwarning("Invalid Interval", "Scan interval must be at least 5 seconds.")
                self.scan_var.set("5")
                return
            config.set('scan_interval', interval)
            messagebox.showinfo("Success", "Scan interval updated. Will take effect on next scan.")
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid number of seconds.")

    def _create_connected_devices_frame(self):
        """Create frame for connected devices."""
        frame = ttk.LabelFrame(self.root, text="Connected Devices", padding="5 5 5 5")
        frame.grid(row=1, column=0, columnspan=4, sticky="nsew", padx=5, pady=5)

        # Create Treeview
        self.devices_tree = ttk.Treeview(frame, columns=(
            "port", "status", "iccid", "network", "phone", "carrier", 
            "signal", "type", "last_seen", "total_activations", 
            "total_earnings", "today_earnings"
        ), show="headings", height=10)

        # Define column headings and widths
        columns = [
            ("port", "Port", 100),
            ("status", "Status", 80),
            ("iccid", "ICCID", 80),
            ("network", "Network", 100),
            ("phone", "Phone", 120),
            ("carrier", "Carrier", 100),
            ("signal", "Signal", 60),
            ("type", "Type", 100),
            ("last_seen", "Last Seen", 150),
            ("total_activations", "Activations", 100),
            ("total_earnings", "Total Earnings", 100),
            ("today_earnings", "Today's Earnings", 100)
        ]

        for col_id, heading, width in columns:
            self.devices_tree.heading(col_id, text=heading)
            self.devices_tree.column(col_id, width=width)

        # Add scrollbar
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.devices_tree.yview)
        self.devices_tree.configure(yscrollcommand=scrollbar.set)

        # Grid layout
        self.devices_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        # Configure grid weights
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        return frame

    def update_devices(self, devices):
        """Update connected devices display."""
        # Clear existing items
        for item in self.devices_tree.get_children():
            self.devices_tree.delete(item)

        # Sort devices by status (active first)
        sorted_devices = sorted(
            devices.items(),
            key=lambda x: (x[1]['status'] != 'active', x[0])
        )

        # Add devices to treeview
        for port, info in sorted_devices:
            # Get activation stats for this phone number
            phone = info.get('phone', 'Unknown')
            if phone != 'Unknown':
                stats = self.server.activation_logger.get_activations_by_phone(phone)
                total_activations = stats['total_activations']
                total_earnings = stats['total_earnings']
                today_earnings = stats['today_earnings']
            else:
                total_activations = 0
                total_earnings = 0.0
                today_earnings = 0.0

            self.devices_tree.insert("", "end", values=(
                port,
                info.get('status', 'Unknown'),
                info.get('iccid', 'Unknown'),
                info.get('network_status', 'Unknown'),
                phone,
                info.get('carrier', 'Unknown'),
                info.get('signal_quality', 'Unknown'),
                info.get('type', 'Unknown'),
                datetime.fromtimestamp(info['last_seen']).strftime('%Y-%m-%d %H:%M:%S'),
                total_activations,
                f"${total_earnings:.2f}",
                f"${today_earnings:.2f}"
            ))

        # Update status counts
        total = len(devices)
        active = sum(1 for d in devices.values() if d['status'] == 'active')
        self.status_var.set(f"Active: {active}/{total}")

    def start_update_thread(self):
        """Start the update thread for periodic updates."""
        def update_loop():
            while True:
                try:
                    # Update device info and server status
                    self.update_queue.put(self.update_device_info)
                    self.update_queue.put(self.update_server_status)
                    # Update earnings views
                    self.update_queue.put(self.update_earnings)
                    
                    # Use the main scan interval setting
                    time.sleep(config.get('scan_interval', 10))
                except Exception as e:
                    logger.error(f"Error in update loop: {e}")

        def check_queue():
            try:
                while True:
                    callback = self.update_queue.get_nowait()
                    callback()
            except queue.Empty:
                pass
            finally:
                self.root.after(1000, check_queue)

        update_thread = threading.Thread(target=update_loop, daemon=True)
        update_thread.start()
        self.root.after(1000, check_queue)

    def update_device_info(self):
        """Update the device information display."""
        try:
            # Clear existing items
            for item in self.devices_tree.get_children():
                self.devices_tree.delete(item)
            
            # Get current modem info directly from modems dictionary
            modems = self.modem_manager.modems
            
            # Update connection state based on active modems
            any_active = any(modem.get('status') == 'active' for modem in modems.values())
            self.connected = any_active
            self.connect_button.config(text="Disconnect All" if any_active else "Connect All")
            
            for port, modem in modems.items():
                # Get modem status and requirements
                status = modem.get('status', 'unknown')
                
                # Get activation stats for this phone number
                phone = modem.get('phone', 'Unknown')
                if phone != 'Unknown':
                    stats = self.server.activation_logger.get_activations_by_phone(phone)
                    total_activations = stats['total_activations']
                    total_earnings = stats['total_earnings']
                    today_earnings = stats['today_earnings']
                else:
                    total_activations = 0
                    total_earnings = 0.0
                    today_earnings = 0.0
                
                # Format carrier info
                carrier = modem.get('carrier', 'Unknown')
                network_status = modem.get('network_status', 'Unknown')
                if carrier == '0':
                    carrier_display = 'Unknown'
                elif carrier.lower() == 'home':
                    carrier_display = f"Home ({network_status})"
                else:
                    carrier_display = f"{carrier} ({network_status})"
                
                # Format signal quality
                signal = modem.get('signal_quality', 'Unknown')
                if signal != 'Unknown':
                    signal_display = f"{signal}%"
                else:
                    signal_display = 'Unknown'
                
                # Insert into tree with colored status
                status_color = 'green' if status == 'active' else 'red'
                item_id = self.devices_tree.insert('', 'end', values=(
                    port,
                    status,
                    modem.get('iccid', 'Unknown'),
                    network_status,
                    phone,
                    carrier_display,
                    signal_display,
                    modem.get('type', 'Unknown'),
                    datetime.fromtimestamp(modem['last_seen']).strftime('%Y-%m-%d %H:%M:%S'),
                    total_activations,
                    f"${total_earnings:.2f}",
                    f"${today_earnings:.2f}"
                ), tags=(status_color,))
                
                # If this was the selected device, reselect it
                if port == self.selected_port:
                    self.devices_tree.selection_set(item_id)
                    self.devices_tree.see(item_id)
            
            # Configure tag colors
            self.devices_tree.tag_configure('green', foreground='green')
            self.devices_tree.tag_configure('red', foreground='red')
                
        except Exception as e:
            logger.error(f"Error updating device info: {e}")
            self.selected_label.config(text=f"Error updating device info: {e}")

    def update_server_status(self):
        """Update the server status information."""
        try:
            # Get service quantities
            service_stats = self.server.get_service_quantities()
            
            # Clear existing items
            for item in self.services_tree.get_children():
                self.services_tree.delete(item)
            
            # Update service statistics
            for service, stats in service_stats.items():
                self.services_tree.insert('', 'end', values=(
                    service,
                    stats['quantity'],
                    stats['active'],
                    stats['completed']
                ))
                
        except Exception as e:
            logger.error(f"Error updating server status: {e}")

    def create_messages_tab(self):
        """Create the message history tab."""
        # Create top frame for controls
        control_frame = ttk.Frame(self.messages_tab)
        control_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        
        # Add modem selection dropdown
        ttk.Label(control_frame, text="Select Modem:").pack(side="left", padx=5)
        self.modem_var = tk.StringVar()
        self.modem_dropdown = ttk.Combobox(control_frame, textvariable=self.modem_var, state="readonly")
        self.modem_dropdown.pack(side="left", padx=5)
        
        # Add refresh button
        ttk.Button(control_frame, text="Refresh", command=self.refresh_message_history).pack(side="right", padx=5)
        
        # Create message history frame
        history_frame = ttk.Frame(self.messages_tab)
        history_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        history_frame.grid_rowconfigure(0, weight=1)
        history_frame.grid_columnconfigure(0, weight=1)
        
        # Create Treeview for message history
        columns = ('timestamp', 'from', 'to', 'message')
        self.history_tree = ttk.Treeview(history_frame, columns=columns, show='headings')
        
        # Define column headings and widths
        headings = {
            'timestamp': ('Time/Date', 150),
            'from': ('From', 150),
            'to': ('To', 150),
            'message': ('Message', 600)
        }
        
        for col, (heading, width) in headings.items():
            self.history_tree.heading(col, text=heading)
            self.history_tree.column(col, width=width, anchor='w' if col == 'message' else 'center')
        
        # Add scrollbars
        y_scrollbar = ttk.Scrollbar(history_frame, orient="vertical", command=self.history_tree.yview)
        x_scrollbar = ttk.Scrollbar(history_frame, orient="horizontal", command=self.history_tree.xview)
        self.history_tree.configure(yscrollcommand=y_scrollbar.set, xscrollcommand=x_scrollbar.set)
        
        # Grid layout
        self.history_tree.grid(row=0, column=0, sticky="nsew")
        y_scrollbar.grid(row=0, column=1, sticky="ns")
        x_scrollbar.grid(row=1, column=0, sticky="ew")
        
        # Bind events
        self.modem_dropdown.bind('<<ComboboxSelected>>', self.on_modem_selected)

    def refresh_message_history(self):
        """Refresh the message history display."""
        try:
            # Update modem list in dropdown
            modems = self.modem_manager.modems
            modem_list = []
            
            # Only include active modems with valid phone numbers
            for port, modem in modems.items():
                if modem.get('status') == 'active':
                    phone = modem.get('phone', 'Unknown')
                    if phone != 'Unknown':
                        # Format: "Phone Number (COM Port)"
                        display_text = f"{phone} ({port})"
                        modem_list.append(display_text)
            
            # Sort the list for easier selection
            modem_list.sort()
            
            # Update dropdown values
            self.modem_dropdown['values'] = modem_list
            
            # If no modem is selected and we have modems, select the first one
            if not self.modem_var.get() and modem_list:
                self.modem_var.set(modem_list[0])
                self.update_message_history()  # Update messages for initial selection
            elif not modem_list:
                # Clear the display if no modems are available
                self.modem_var.set('')
                for item in self.history_tree.get_children():
                    self.history_tree.delete(item)
            
        except Exception as e:
            logger.error(f"Error refreshing message history: {e}")

    def update_message_history(self):
        """Update the message history display for the selected modem."""
        try:
            # Clear current display
            for item in self.history_tree.get_children():
                self.history_tree.delete(item)
            
            selected = self.modem_var.get()
            if not selected:
                return
                
            # Extract port from selection (format: "phone (port)")
            port = selected.split('(')[-1].rstrip(')')
            
            # Get messages for this modem
            messages = self.modem_manager.check_sms(port)
            if not messages:
                return
            
            # Get phone number for this modem
            modem_info = self.modem_manager.modems.get(port, {})
            phone_number = modem_info.get('phone', 'Unknown')
            
            # Update display with newest messages first
            for msg in reversed(messages):
                timestamp = msg.get('timestamp', 'Unknown')
                # Format timestamp if it's not already formatted
                if isinstance(timestamp, str) and not timestamp.lower() == 'unknown':
                    try:
                        # Try to parse and reformat the timestamp
                        dt = datetime.strptime(timestamp, '%y/%m/%d,%H:%M:%S')
                        timestamp = dt.strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        pass  # Keep original format if parsing fails
                
                self.history_tree.insert('', 0, values=(
                    timestamp,
                    msg.get('sender', 'Unknown'),
                    phone_number,
                    msg.get('text', '')
                ))
                
        except Exception as e:
            logger.error(f"Error updating message history: {e}")

    def on_modem_selected(self, event):
        """Handle modem selection change."""
        self.update_message_history()

    def create_earnings_tab(self):
        """Create the earnings tab."""
        # Create earnings tab frame
        earnings_frame = ttk.Frame(self.earnings_tab)
        earnings_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        
        # Create earnings sub-tabs
        self.timeframe_tab = EarningsPage(earnings_frame, self.server)
        self.service_tab = EarningsPage(earnings_frame, self.server)
        self.phone_tab = EarningsPage(earnings_frame, self.server)
        
        # Configure sub-tabs
        self.timeframe_tab.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        self.service_tab.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
        self.phone_tab.grid(row=0, column=2, padx=5, pady=5, sticky="nsew")

    def run(self):
        """Start the GUI application."""
        # Initial device scan
        self.scan_devices()
        
        # Start the main event loop
        self.root.mainloop()

    def update_earnings(self):
        """Update all earnings views."""
        try:
            self.timeframe_tab.update()
            self.service_tab.update()
            self.phone_tab.update()
        except Exception as e:
            logger.error(f"Error updating earnings views: {e}")

class EarningsPage(ttk.Frame):
    def __init__(self, parent, server):
        super().__init__(parent)
        self.server = server
        self._create_timeframe_view()
        self._create_service_view()
        self._create_phone_view()
        
    def _create_timeframe_view(self):
        frame = ttk.LabelFrame(self, text="Earnings by Time Period")
        frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        
        self.timeframe_tree = ttk.Treeview(frame, columns=("period", "amount"), show="headings")
        self.timeframe_tree.heading("period", text="Time Period")
        self.timeframe_tree.heading("amount", text="Earnings")
        self.timeframe_tree.grid(row=0, column=0, sticky="nsew")
        
    def _create_service_view(self):
        frame = ttk.LabelFrame(self, text="Earnings by Service")
        frame.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
        
        self.service_tree = ttk.Treeview(frame, columns=("service", "amount"), show="headings")
        self.service_tree.heading("service", text="Service")
        self.service_tree.heading("amount", text="Earnings")
        self.service_tree.grid(row=0, column=0, sticky="nsew")
        
    def _create_phone_view(self):
        frame = ttk.LabelFrame(self, text="Earnings by Phone Number")
        frame.grid(row=0, column=2, padx=5, pady=5, sticky="nsew")
        
        self.phone_tree = ttk.Treeview(frame, columns=("phone", "amount"), show="headings")
        self.phone_tree.heading("phone", text="Phone Number")
        self.phone_tree.heading("amount", text="Earnings")
        self.phone_tree.grid(row=0, column=0, sticky="nsew")
        
    def update(self):
        # Clear existing items
        for tree in (self.timeframe_tree, self.service_tree, self.phone_tree):
            for item in tree.get_children():
                tree.delete(item)
                
        # Update timeframe view
        timeframes = {
            'Today': 'day',
            'Last 7 Days': 'week',
            'Last 30 Days': 'month',
            'Last Year': 'year',
            'All Time': 'all'
        }
        
        for label, timeframe in timeframes.items():
            earnings = self.server.activation_logger.get_earnings_by_timeframe(timeframe)
            self.timeframe_tree.insert("", "end", values=(label, f"${earnings:.2f}"))
            
        # Update service view
        service_earnings = self.server.activation_logger.get_earnings_by_service()
        for service, earnings in service_earnings.items():
            self.service_tree.insert("", "end", values=(service, f"${earnings:.2f}"))
            
        # Update phone view
        phone_earnings = self.server.activation_logger.get_earnings_by_phone()
        for phone, earnings in phone_earnings.items():
            self.phone_tree.insert("", "end", values=(phone, f"${earnings:.2f}"))