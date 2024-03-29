from . import transport
from typing import Callable
class BridgeTransport:
	"""Object to bridge two transports together,
	passing messages to both of them.
	We exclude transport-specific messages such as client_joined."""
	excluded = ('client_joined', 'client_left', 'channel_joined', 'set_braille_info')

	def __init__(self, t1: transport.Transport, t2: transport.Transport):
		self.t1 = t1
		self.t2 = t2
		t1.callback_manager.register_callback('*', self.send_to_t2)
		t2.callback_manager.register_callback('*', self.send_to_t1)

	def send(self, transport: transport.Transport, callback: str, *args, **kwargs) -> None:
		if not callback.startswith('msg_'):
			return
		msg = callback.split('_', 1)[-1]
		if msg in self.excluded:
			return
		transport.send(msg, *args, **kwargs)

	def send_to_t2(self, callback: str, *args, **kwargs) -> None:
		self.send(self.t2, callback, *args, **kwargs)

	def send_to_t1(self, callback: str, *args, **kwargs) -> None:
		self.send(self.t1, callback, *args, **kwargs)

	def disconnect(self) -> None:
		self.t1.callback_manager.unregister_callback('*', self.send_to_t2)
		self.t2.callback_manager.unregister_callback('*', self.send_to_t1)
