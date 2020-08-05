import plotly
import plotly.graph_objs as go
import pandas as pd
import numpy as np
import json
from rti_python.Comm.adcp_serial_port import AdcpSerialPort
import rti_python.Comm.adcp_serial_port as serial_port
from rti_python.Codecs.AdcpCodec import AdcpCodec
import threading
import logging
import serial
import time
import datetime
from collections import deque


class AppManager:

    def __init__(self, socketio, plotly_dash):
        self.plot = self.create_plot()
        self.socketio = socketio
        self.plotly_dash = plotly_dash

        # ADCP Codec to decode the ADCP data
        self.adcp_codec = AdcpCodec()
        self.adcp_codec.ensemble_event += self.process_ensemble

        # Serial Port
        self.serial_port = None
        self.serial_thread = None
        self.serial_thread_alive = False

        self.app_state = {
            "is_serial_connected": False,                       # Is the serial port connected
            "serial_status": [],                                # Status of the serial connection
            "selected_serial_port": "",                         # Comm port selected
            "selected_baud": "115200",                          # Baud rate selected
            "is_serial_error":  False,                          # Any serial errors.
            "serial_error_status": [],                          # List of error messages
            "baud_list": self.get_baud_rates(),                 # List of all available Baud rates
            "serial_port_list": self.get_serial_ports(),        # List of all available Serial Ports
            "serial_raw_ascii": "",                             # Raw ascii from the serial port
            "adcp_break": {},                                   # Results of a BREAK statement
            "adcp_ens_num": 0,                                  # Latest Ensemble number
        }

        self.is_volt_plot_init = False
        self.voltage_queue = deque(maxlen=100)
        self.ens_dt_queue = deque(maxlen=100)

        # Incoming serial data
        self.serial_raw_bytes = None

    def get_plot(self):
        return self.plot

    def create_plot(self):
        N = 40
        x = np.linspace(0, 1, N)
        y = np.random.randn(N)
        df = pd.DataFrame({'x': x, 'y': y})  # creating a sample dataframe

        data = [
            go.Bar(
                x=df['x'],  # assign x as the dataframe column 'x'
                y=df['y']
            )
        ]

        graphJSON = json.dumps(data, cls=plotly.utils.PlotlyJSONEncoder)

        return graphJSON

    def socketio_background_thread(self):
        """
        Background worker.  This will maintain the status of the
        backend and the GUI.
        Send the status of the Datalogger download process.
        This will continously check the status of the process.
        """
        count = 0
        while True:
            # Wait time
            self.socketio.sleep(5)
            count += 1

            # Send a debug status to websocket
            self.socketio.emit('status_report',
                               {'data': 'Server generated event', 'count': count},
                               namespace='/rti')

    def get_serial_ports(self):
        return serial_port.get_serial_ports()

    def get_baud_rates(self):
        return serial_port.get_baud_rates()

    def connect_serial(self, comm_port: str, baud: int):
        """
        Connect the serial port.
        Start the serial port read thread.
        """
        # Set App State
        self.app_state["selected_serial_port"] = comm_port
        self.app_state["selected_baud"] = str(baud)

        if not self.serial_port:
            try:
                self.serial_port = AdcpSerialPort(comm_port, baud)
            except ValueError as ve:
                logging.error("Error opening serial port. " + str(ve))
                self.app_state["is_serial_connected"] = False
                self.app_state["is_serial_error"] = True
                self.app_state["serial_error_status"].append("Error opening serial port. " + str(ve))
                return self.app_state
            except serial.SerialException as se:
                logging.error("Error opening serial port. " + str(se))
                self.app_state["is_serial_connected"] = False
                self.app_state["is_serial_error"] = True
                self.app_state["serial_error_status"].append("Error opening serial port. " + str(se))
                return self.app_state
            except Exception as e:
                logging.error("Error opening serial port. " + str(e))
                self.app_state["is_serial_connected"] = False
                self.app_state["is_serial_error"] = True
                self.app_state["serial_error_status"].append("Error opening serial port. " + str(e))
                return self.app_state

            # Start the read thread
            self.serial_thread_alive = True
            self.serial_thread = threading.Thread(name="Serial Terminal Thread", target=self.serial_thread_worker)
            self.serial_thread.start()

            # Set the app state
            self.app_state["is_serial_connected"] = True
            self.app_state["is_serial_error"] = False
            self.app_state["serial_status"].clear()
            self.app_state["serial_status"].append("Connected")

            return self.app_state

    def disconnect_serial(self):
        """
        Disconnect the serial port.
        """
        self.serial_thread_alive = False

        if self.serial_port:
            self.serial_port.disconnect()
            self.serial_port = None

            # Set the app state
            self.app_state["is_serial_connected"] = False
            self.app_state["is_serial_error"] = False
            self.app_state["serial_status"].clear()
            self.app_state["serial_error_status"].clear()
            self.app_state["serial_status"].append("Disconnected")

        return self.app_state

    def send_serial_break(self):
        if self.serial_port:

            # Clear the buffer of the serial data
            # We can then check for the results
            self.app_state["serial_raw_ascii"] = ""

            self.serial_port.send_break()

            # Wait a second for result
            time.sleep(1.2)

            # Get the results of the BREAK
            break_results = self.app_state["serial_raw_ascii"]
            logging.debug(break_results)

            # Decode the BREAK result
            self.app_state["adcp_break"] = self.adcp_codec.decode_BREAK(break_results)
            logging.debug(self.app_state["adcp_break"])

            return self.app_state["adcp_break"]

    def send_serial_cmd(self, cmd):
        if self.serial_port:
            self.serial_port.send_cmd(cmd=cmd)

    def process_ensemble(self, sender, ens):
        if ens.IsEnsembleData:
            print(str(ens.EnsembleData.EnsembleNumber))
            self.app_state["adcp_ens_num"] = ens.EnsembleData.EnsembleNumber

            # Pass the ASCII serial data to the websocket
            self.socketio.emit('adcp_ens',
                               {
                                   'adcp_ens_num': self.app_state["adcp_ens_num"]
                               },
                               namespace='/rti')

            # Display the voltage live
            if not self.is_volt_plot_init:
                self.socketio.emit('bootstrap',
                                   {'x': [ens.EnsembleData.datetime_str()], 'y': [0]}, namespace='/rti')
                self.is_volt_plot_init = True

            datetime_now = ens.EnsembleData.datetime().strftime("%Y-%m-%d %H:%M:%S.%f")
            voltage = ens.SystemSetup.Voltage
            self.voltage_queue.append(voltage)
            self.ens_dt_queue.append(datetime_now)
            self.socketio.emit('update_plot', {'x': list(self.ens_dt_queue), 'y': list(self.voltage_queue)}, namespace='/rti')

            # Add data to Plotly Dashboard
            self.plotly_dash.add_ens(ens)

    def serial_thread_worker(self):
        """
        Thread worker to handle reading the serial port.
        :param mgr: This Object to get access to the variables.
        :return:
        """
        while self.serial_thread_alive:
            try:
                if self.serial_port.raw_serial.in_waiting:
                    # Read the data from the serial port
                    self.serial_raw_bytes = self.serial_port.read(self.serial_port.raw_serial.in_waiting)

                    try:
                        # Convert the data to ASCII
                        self.app_state["serial_raw_ascii"] = self.serial_raw_bytes.decode('ascii')

                        # Pass the ASCII serial data to the websocket
                        self.socketio.emit('serial_comm',
                                           {
                                               'data': self.app_state["serial_raw_ascii"]
                                           },
                                           namespace='/rti')

                    except Exception as ex:
                        # Do nothing
                        # This is to prevent from seeing binary data on screen
                        logging.info("Error Reading serial data" + str(ex))


                    # Record data if turned on
                    #vm.record_data(data)

                    # Record the raw data if turned on

                    # Pass data to codec to decode ADCP data
                    self.adcp_codec.add(self.serial_raw_bytes)

                # Put a small sleep to allow more data to go into the buffer
                time.sleep(0.01)

            except serial.SerialException as se:
                logging.error("Error using the serial port.\n" + str(se))
                self.disconnect_serial()
            except Exception as ex:
                logging.error("Error processing the data.\n" + str(ex))
                self.disconnect_serial()
