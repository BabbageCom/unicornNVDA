import threading
import time
import queue
import ssl
import socket
import select
from logHandler import log
from . import callback_manager
import ctypes.wintypes
from . import unicorn
from . import serializer
import core
from typing import Union, Iterable, List
from enum import Enum
import speech.commands

PROTOCOL_VERSION = 2
#DVCTYPES = ('slave', 'master')

class DVCTYPES(Enum):
	slave = "slave"
	master = "master"


class Transport:

	def __init__(self, serializer: serializer.JSONSerializer):
		self.serializer = serializer
		self.callback_manager = callback_manager.CallbackManager()
		self.connected = False
		self.successful_connects = 0

	def transport_connected(self) -> None:
		self.successful_connects += 1
		self.connected = True
		self.callback_manager.call_callbacks('transport_connected')

	def send(self, type: str, *args, **kwargs) -> None:
		pass

	def run(self):
		pass

class TCPTransport(Transport):

	def __init__(self, serializer, address, timeout=0):
		super().__init__(serializer=serializer)
		self.closed = False
		# Buffer to hold partially received data
		self.buffer = ""
		self.queue = queue.Queue()
		self.address = address
		self.server_sock = None
		self.queue_thread = None
		self.timeout = timeout
		self.reconnector_thread = ConnectorThread(self)

	def run(self):
		self.closed = False
		try:
			self.server_sock = self.create_outbound_socket(self.address)
			self.server_sock.connect(self.address)
		except Exception:
			self.callback_manager.call_callbacks('transport_connection_failed')
			raise
		self.transport_connected()
		self.queue_thread = threading.Thread(target=self.send_queue)
		self.queue_thread.daemon = True
		self.queue_thread.start()
		while self.server_sock is not None:
			try:
				readers, writers, error = select.select([self.server_sock], [], [self.server_sock])
			except OSError:
				self.buffer = ""
				break
			if self.server_sock in error:
				self.buffer = ""
				break
			if self.server_sock in readers:
				try:
					self.handle_server_data()
				except OSError:
					self.buffer = ""
					break
		self.connected = False
		self.callback_manager.call_callbacks('transport_disconnected')
		self._disconnect()

	def create_outbound_socket(self, address):
		address = socket.getaddrinfo(*address)[0]
		server_sock = socket.socket(*address[:3])
		if self.timeout:
			server_sock.settimeout(self.timeout)
		server_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
		server_sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, 60000, 2000))
		server_sock = ssl.wrap_socket(server_sock)
		return server_sock

	def handle_server_data(self):
		data = self.buffer + self.server_sock.recv(16384).decode(errors="surrogatepass")
		self.buffer = ""
		if data == '':
			self._disconnect()
			return
		if '\n' not in data:
			self.buffer += data
			return
		while '\n' in data:
			line, sep, data = data.partition('\n')
			self.parse(line)
		self.buffer += data

	def parse(self, line):
		obj = self.serializer.deserialize(line)
		if 'type' not in obj:
			return
		callback = "msg_" + obj['type']
		del obj['type']
		self.callback_manager.call_callbacks(callback, **obj)

	def send_queue(self):
		while True:
			item = self.queue.get()
			if item is None:
				return
			try:
				self.server_sock.sendall(item.encode(errors="surrogatepass"))
			except OSError:
				return

	def send(self, type, **kwargs):
		obj = self.serializer.serialize(type=type, **kwargs)
		if self.connected:
			self.queue.put(obj)

	def _disconnect(self):
		"""Disconnect the transport due to an error, without closing the connector thread."""
		if not self.connected:
			return
		if self.queue_thread is not None:
			self.queue.put(None)
			self.queue_thread.join()
		clear_queue(self.queue)
		self.server_sock.close()
		self.server_sock = None

	def close(self):
		self.callback_manager.call_callbacks('transport_closing')
		self.reconnector_thread.running = False
		self._disconnect()
		self.closed = True
		self.reconnector_thread = ConnectorThread(self)


class RelayTransport(TCPTransport):

	def __init__(self, serializer, address, timeout=0, channel=None, connection_type=None, protocol_version=PROTOCOL_VERSION):
		super().__init__(address=address, serializer=serializer, timeout=timeout)
		log.info(f"Connecting to {address} channel {channel}")
		self.channel = channel
		self.connection_type = connection_type
		self.protocol_version = protocol_version
		self.callback_manager.register_callback('transport_connected', self.on_connected)

	def on_connected(self):
		self.send('protocol_version', version=self.protocol_version)
		if self.channel is not None:
			self.send('join', channel=self.channel, connection_type=self.connection_type)
		else:
			self.send('generate_key')


class DVCTransport(Transport, unicorn.UnicornCallbackHandler):

	def __init__(
			self,
			serializer: serializer.JSONSerializer,
			connection_type: unicorn.CTYPE,
			timeout: int = 60,
			protocol_version: int = PROTOCOL_VERSION,
			maxBytes: int = 4096
		):
		Transport.__init__(self, serializer=serializer)
		unicorn.UnicornCallbackHandler.__init__(self)

		log.info(f"Connecting to DVC as {connection_type}")
		self.lib = unicorn.Unicorn(connection_type, self)
		self.opened = False
		self.initialized = False
		# Buffer to hold partially received data
		self.buffer = ""
		self.queue = queue.Queue()
		self.queue_thread = None
		self.interrupt_event = threading.Event()
		self.timeout = timeout
		self.reconnector_thread = ConnectorThread(self, run_except=EnvironmentError)
		self.connection_type = connection_type
		self.protocol_version = protocol_version
		self.callback_manager.register_callback('msg_protocol_version', self.handle_p2p)
		self.initialize_lib()
		# F_Giepmans, 15-11-2022: Temporary fix for Citrix enviroments where the max buffer length is reached.
		self.maxBytes = maxBytes

	def initialize_lib(self) -> None:
		if self.initialized:
			return
		res = self.lib.Initialize()
		if res:
			raise ctypes.WinError(res)
		self.initialized = True

	def terminate_lib(self) -> None:
		if not self.initialized:
			return
		res = self.lib.Terminate()
		if res:
			raise ctypes.WinError(res)
		self.initialized = False

	def run(self) -> None:
		self.interrupt_event.clear()
		res = self.lib.Open()
		if res >= 1 << 31:
			raise OSError("Raised WinError %s out of range" % hex(res))
		elif res in (1, 87):
			self.callback_manager.call_callbacks('transport_connection_failed')
			raise ctypes.WinError(res)
		elif res:
			raise ctypes.WinError(res)
		if self.connection_type == unicorn.CTYPE.CLIENT and not unicorn.unicorn_client():  # Master
			self.callback_manager.call_callbacks('transport_connection_failed')
			raise ctypes.WinError(res)
		self.opened = True
		self.queue_thread = threading.Thread(target=self.send_queue)
		self.queue_thread.daemon = True
		self.queue_thread.start()
		self.interrupt_event.wait()
		self.callback_manager.call_callbacks('transport_disconnected')
		self._disconnect()

	def handle_data(self, string: str) -> None:
		data = self.buffer + string
		self.buffer = ""
		if data == '':
			self._disconnect()
			return
		if '\n' not in data:
			self.buffer += data
			return
		while '\n' in data:
			line, sep, data = data.partition('\n')
			self.parse(line)
		self.buffer += data

	def parse(self, line):
		# deserialize object needs the transporter for callback commands. If there is a sequence with a callback command
		# it should be able to directly call the send method of the transporter.
		obj = self.serializer.deserialize(line)
		if 'type' not in obj:
			return
		if 'sequence' in obj:
			obj['sequence'] = self.replaceCallbacksPlaceholdersWithActualCallbacks(obj['sequence'])
		callback = "msg_" + obj['type']
		del obj['type']
		self.callback_manager.call_callbacks(callback, **obj)

	def replaceCallbacksPlaceholdersWithActualCallbacks(self, sequence: List) -> List:
		# callback-bounce commands are embedded in the deserialized speech sequence, but need to be translated into
		# actually callable functions.
		newSequence = []
		for item in sequence:
			if isinstance(item, serializer.callBackCommandBounce):
				newSequence.append(self.makeCallBackCommandWrapper(item.compName, item.index))
			else:
				newSequence.append(item)
		return newSequence

	def makeCallBackCommandWrapper(
			self,
			compName: str,
			index: int
	) -> speech.commands.CallbackCommand:
		def _callBackWrapper(computerName: str = compName, ii: int = index) -> None:
			self.send(type="callbackCommandBounce", compName=computerName, index=ii)

		return speech.commands.CallbackCommand(_callBackWrapper)

	def send_queue(self) -> None:
		while True:
			item = self.queue.get()
			if item is None:
				return
			strbuf = ctypes.create_unicode_buffer(item)
			if ctypes.sizeof(strbuf) > self.maxBytes:
				log.error(f"data packet is to big for unicorn to handle! package: \n {item}")
				continue
			res = self.lib.Write(ctypes.sizeof(strbuf), ctypes.cast(strbuf, ctypes.POINTER(ctypes.wintypes.BYTE)))
			if res:
				log.warning(ctypes.WinError(res))
				# return

	def send(self, type: str, origin: int = -1, **kwargs) -> None:
		obj = self.serializer.serialize(type=type, origin=origin, **kwargs)
		if self.connected:
			self.queue.put(obj)

	def _disconnect(self) -> None:
		if not self.connected and not self.opened:
			return
		self.interrupt_event.set()
		# Closing in this context is the equivalent for disconnecting the transport
		res = self.lib.Close()
		if res not in (0, 21):
			log.warning(ctypes.WinError(res))
		if self.queue_thread is not None:
			self.queue.put(None)
			self.queue_thread.join()
		clear_queue(self.queue)
		self.connected = False
		self.opened = False

	def close(self) -> None:
		self.callback_manager.call_callbacks('transport_closing')
		self.reconnector_thread.running = False
		self._disconnect()
		# Terminating in this context is the equivalent for closing the transport
		res = self.terminate_lib()
		if res:
			raise ctypes.WinError(res)
		self.reconnector_thread = ConnectorThread(self, run_except=EnvironmentError)

	def handle_p2p(self, version: int, **kwargs) -> None:
		if version == PROTOCOL_VERSION:
			self.send(type='client_joined', client=dict(id=-1, connection_type=self.connection_type))
		else:
			self.send(type='version_mismatch')

	def _Connected(self) -> int:
		log.info("Connected to remote protocol server")
		return 0

	def _Disconnected(self, dwDisconnectCode) -> int:
		log.warning("Disconnected from remote protocol server")
		self._disconnect()
		return 0

	def _Terminated(self) -> int:
		log.info("Remote protocol client terminated")
		self._disconnect()
		return 0

	def _OnNewChannelConnection(self) -> int:
		log.info("DVC connection initiated from remote protocol server")
		self.transport_connected()
		self.send('protocol_version', version=self.protocol_version)
		return 0

	def _OnDataReceived(self, cbSize: int, pBuffer: ctypes.POINTER(ctypes.wintypes.BYTE) ) -> int:
		pBuffer = ctypes.cast(pBuffer, ctypes.POINTER(ctypes.c_wchar * (cbSize // ctypes.sizeof(ctypes.c_wchar))))
		string = "".join(pBuffer.contents)
		if "\x00" not in string:
			self.buffer += string
		else:
			self.handle_data(string.replace("\x00", ""))
		return 0

	def _OnReadError(self, dwError) -> int:
		log.warning("Error reading from DVC, %d" % dwError)
		self.interrupt_event.set()
		return 0

	def _OnClose(self) -> int:
		log.info("DVC close request received")
		self.callback_manager.call_callbacks('msg_client_left', client=dict(id=-1))
		self._disconnect()
		return 0

	def _OnTrial(self) -> None:
		core.callLater(2000, self.callback_manager.call_callbacks, 'transport_connection_in_trial_mode')

	def _OnTrialExpired(self) -> None:
		self.callback_manager.call_callbacks('transport_trial_expired')


class ConnectorThread(threading.Thread):

	def __init__(self, connector: Transport, connect_delay: int = 5, run_except: type(OSError) = socket.error):
		super().__init__()
		self.connect_delay = connect_delay
		self.run_except = run_except
		self.running = True
		self.connector = connector
		self.name = self.name + "_connector_loop"
		self.daemon = True

	def run(self) -> None:
		while self.running:
			try:
				self.connector.run()
			except self.run_except:
				log.debugWarning("Connection failed", exc_info=True)
				time.sleep(self.connect_delay)
				continue
			else:
				time.sleep(self.connect_delay)
		log.info("Ending control connector thread %s" % self.name)


def clear_queue(queue: queue.Queue) -> None:
	try:
		while True:
			queue.get_nowait()
	except Exception:
		pass
