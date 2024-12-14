import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import queue
import time
import logging
from smshub_integration import SmsHubIntegration
from config import SMSHUB_API_KEY, config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ModemGUI(ttk.Frame):
    def __init__(self, modem_manager, server):
        """Initialize the GUI."""
        self.root = tk.Tk()
        super().__init__(self.root)
        self.root.title("SMS Hub Agent")
        self.root.geometry("1300x900")  # Set a reasonable default size
        
        # Initialize managers
        self.modem_manager = modem_manager
        self.server = server
        self.smshub = server.smshub
        
        # Initialize state variables
        self.selected_port = None
        self.connected = False
        self.update_queue = queue.Queue()
        
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Create tabs
        self.device_tab = ttk.Frame(self.notebook)
        self.server_tab = ttk.Frame(self.notebook)
        
        self.notebook.add(self.device_tab, text="Device Management")
        self.notebook.add(self.server_tab, text="SMS Hub Dashboard")
        
        # Create tab contents
        self.create_device_tab()
        self.create_server_tab()
        
        # Start update thread
        self.start_update_thread()

    def create_widgets(self):
        # Create main container with notebook for tabs
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)

        # Create tabs
        self.devices_tab = ttk.Frame(self.notebook)
        self.server_tab = ttk.Frame(self.notebook)
        
        self.notebook.add(self.devices_tab, text="Devices")
        self.notebook.add(self.server_tab, text="Server Status")

        # Create widgets for each tab
        self.create_devices_tab()
        self.create_server_tab()

        # Create tunnel status frame at the bottom of the main window
        self.tunnel_frame = ttk.LabelFrame(self, text="Tunnel Status")
        self.tunnel_frame.pack(fill='x', padx=5, pady=5)

        self.tunnel_status_label = ttk.Label(self.tunnel_frame, text="LocalToNet Status:")
        self.tunnel_status_label.pack(side='left', padx=5)

        self.tunnel_url_label = ttk.Label(self.tunnel_frame, text="Not Connected")
        self.tunnel_url_label.pack(side='left', padx=5)

    def create_device_tab(self):
        """Create the device management tab."""
        # Device List Frame
        list_frame = ttk.LabelFrame(self.device_tab, text="Connected Devices", padding="5")
        list_frame.pack(fill="x", padx=5, pady=5)
        
        # Create Treeview for devices
        columns = ('status', 'com_port', 'imei', 'phone', 'signal', 'modem_status')
        self.device_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=5)
        
        # Define column headings and widths
        headings = {
            'status': ('Status', 100),
            'com_port': ('COM Port', 100),
            'imei': ('IMEI', 150),
            'phone': ('Phone Number', 150),
            'signal': ('Signal', 100),
            'modem_status': ('Modem Status', 150)
        }
        
        for col, (heading, width) in headings.items():
            self.device_tree.heading(col, text=heading)
            self.device_tree.column(col, width=width, anchor='center')
        
        self.device_tree.pack(fill="x", padx=5, pady=5)
        self.device_tree.bind('<<TreeviewSelect>>', self.on_select)
        
        # Control Frame
        control_frame = ttk.Frame(self.device_tab)
        control_frame.pack(fill="x", padx=5, pady=5)
        
        # Status Label
        self.selected_label = ttk.Label(control_frame, text="No device selected")
        self.selected_label.pack(side="left", padx=5)
        
        # Control Buttons
        self.connect_button = ttk.Button(control_frame, text="Connect All", command=self.toggle_connections)
        self.connect_button.pack(side="right", padx=5)
        
        ttk.Button(control_frame, text="Scan", command=self.scan_devices).pack(side="right", padx=5)
        
        # Messages Frame
        msg_frame = ttk.LabelFrame(self.device_tab, text="Device Messages", padding="5")
        msg_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Create Treeview for messages
        columns = ('timestamp', 'sender', 'message', 'status')
        self.msg_tree = ttk.Treeview(msg_frame, columns=columns, show='headings', height=10)
        
        # Define column headings and widths
        headings = {
            'timestamp': ('Time', 150),
            'sender': ('Sender', 150),
            'message': ('Message', 400),
            'status': ('Status', 100)
        }
        
        for col, (heading, width) in headings.items():
            self.msg_tree.heading(col, text=heading)
            self.msg_tree.column(col, width=width, anchor='w' if col == 'message' else 'center')
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(msg_frame, orient="vertical", command=self.msg_tree.yview)
        self.msg_tree.configure(yscrollcommand=scrollbar.set)
        
        self.msg_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

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

    def register_selected_modem(self):
        """Register selected modem with SMS Hub."""
        if not self.selected_port:
            self.selected_label.config(text="Please select a device first")
            return

        # Get device info
        for item in self.device_tree.get_children():
            values = self.device_tree.item(item)['values']
            if values[1] == self.selected_port:  # Check COM port
                phone_number = values[3]  # Phone number is at index 3
                if phone_number and phone_number != 'N/A':
                    # Register with SMS Hub integration
                    if self.smshub.register_modem(self.selected_port, phone_number):
                        # Register with server
                        if self.server.register_modem(phone_number):
                            self.selected_label.config(text=f"Registered {self.selected_port} with SMS Hub")
                            self.update_device_info()
                        else:
                            self.selected_label.config(text=f"Failed to register {self.selected_port} with server")
                    else:
                        self.selected_label.config(text=f"Failed to register {self.selected_port} with SMS Hub")
                else:
                    self.selected_label.config(text="No phone number available")
                break

    def update_device_info(self):
        """Update the device information display."""
        try:
            # Clear existing items
            for item in self.device_tree.get_children():
                self.device_tree.delete(item)
            
            # Get current modem info
            modems = self.modem_manager.get_modems()
            
            # Update connection state based on active modems
            any_active = any(modem.get('status') == 'active' for modem in modems.values())
            self.connected = any_active
            self.connect_button.config(text="Disconnect All" if any_active else "Connect All")
            
            for port, modem in modems.items():
                # Get modem status
                status = modem.get('status', 'unknown')
                status_color = 'green' if status == 'active' else 'red'
                
                # Format phone number
                phone = modem.get('phone', 'Unknown')
                if phone == 'Unknown':
                    phone_display = 'Not Available'
                else:
                    phone_display = phone
                
                # Get modem status display
                modem_status = "Active" if status == 'active' else "Inactive"
                
                # Insert into tree with colored status
                item_id = self.device_tree.insert('', 'end', values=(
                    status,
                    port,
                    modem.get('imsi', 'Unknown'),
                    phone_display,
                    modem.get('signal', 'Unknown'),
                    modem_status
                ), tags=(status_color,))
                
                # If this was the selected device, reselect it
                if port == self.selected_port:
                    self.device_tree.selection_set(item_id)
                    self.device_tree.see(item_id)
            
            # Configure tag colors
            self.device_tree.tag_configure('green', foreground='green')
            self.device_tree.tag_configure('red', foreground='red')
            
            # Update messages if needed
            if self.selected_port:
                self.refresh_messages()
                
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

    def process_new_message(self, modem_id: str, message: dict):
        """Process a new message and update the display."""
        # Update local display
        self.refresh_messages()
        
        # Get phone number for the modem
        phone_number = None
        for item in self.device_tree.get_children():
            values = self.device_tree.item(item)['values']
            if values[1] == modem_id:  # COM port
                phone_number = values[3]  # Phone number
                break
        
        if phone_number and phone_number != 'Not Available':
            # Add message to server queue
            self.server.add_message(phone_number, message)
        
        # Update device info to reflect any changes
        self.update_device_info()

    def start_update_thread(self):
        def update_loop():
            while True:
                try:
                    # Update device info and server status
                    self.update_queue.put(self.update_device_info)
                    self.update_queue.put(self.update_server_status)
                    
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

    def run(self):
        """Start the GUI application."""
        # Initial device scan
        self.scan_devices()
        
        # Start the main event loop
        self.root.mainloop()

    def on_select(self, event):
        """Handle device selection."""
        selection = self.device_tree.selection()
        if selection:
            item = self.device_tree.item(selection[0])
            new_port = item['values'][1]  # COM port is at index 1
            
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
            new_ports = self.modem_manager.find_franklin_t9_devices()
            if new_ports:
                self.selected_label.config(text=f"Found Franklin T9 devices: {', '.join(new_ports)}")
            else:
                self.selected_label.config(text="No Franklin T9 devices found")
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