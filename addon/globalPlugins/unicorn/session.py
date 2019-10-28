import threading
import time
import speech
import braille
from . import nvda_patcher
from collections import defaultdict
import tones
import synthDriverHandler


class RemoteSession(object):

	def __init__(self, local_machine, transport):
		self.local_machine = local_machine
		self.patcher = None
		self.transport = transport


class SlaveSession(RemoteSession):
	"""Session that runs on the slave and manages state."""

	def __init__(self, *args, is_secondary=False, **kwargs):
		super(SlaveSession, self).__init__(*args, **kwargs)
		self.transport.callback_manager.register_callback('msg_client_joined', self.handle_client_connected)
		self.transport.callback_manager.register_callback('msg_client_left', self.handle_client_disconnected)
		self.masters = defaultdict(dict)
		self.master_display_sizes = []
		self.transport.callback_manager.register_callback('transport_disconnected', self.handle_disconnected)
		self.transport.callback_manager.register_callback('transport_closing', self.handle_transport_closing)
		self.patcher = nvda_patcher.NVDASlavePatcher(is_secondary=is_secondary)
		self.patch_callbacks_added = False
		self.transport.callback_manager.register_callback('msg_channel_joined', self.handle_channel_joined)
		self.transport.callback_manager.register_callback('msg_set_braille_info', self.handle_braille_info)
		self.transport.callback_manager.register_callback('msg_set_display_size', self.set_display_size)
		self.transport.callback_manager.register_callback('msg_braille_input', self.local_machine.braille_input)

	def handle_client_connected(self, client=None, **kwargs):
		self.patcher.patch()
		if not self.patch_callbacks_added:
			self.add_patch_callbacks()
			self.patch_callbacks_added = True
		tones.beep(1000, 300)
		if client['connection_type'] == 'master':
			self.masters[client['id']]['active'] = True

	def handle_channel_joined(self, channel=None, clients=None, origin=None, **kwargs):
		if clients is None:
			clients = []
		for client in clients:
			self.handle_client_connected(client)

	def handle_disconnected(self):
		self.masters.clear()

	def handle_transport_closing(self):
		self.patcher.unpatch()
		if self.patch_callbacks_added:
			self.remove_patch_callbacks()
			self.patch_callbacks_added = False

	def handle_client_disconnected(self, client=None, **kwargs):
		tones.beep(108, 300)
		if client['connection_type'] == 'master':
			del self.masters[client['id']]
		if not self.masters:
			self.patcher.unpatch()

	def set_display_size(self, sizes=None, **kwargs):
		self.master_display_sizes = sizes if sizes else [info.get("braille_numCells", 0) for info in self.masters.values()]
		self.local_machine.set_braille_display_size(self.master_display_sizes)

	def handle_braille_info(self, name=None, numCells=0, origin=None, **kwargs):
		if not self.masters.get(origin):
			return
		self.masters[origin]['braille_name'] = name
		self.masters[origin]['braille_numCells'] = numCells
		self.set_display_size()

	def add_patch_callbacks(self):
		patcher_callbacks = (
			('speak', self.speak),
			('cancel_speech', self.cancel_speech),
			('display', self.display),
			('set_display', self.set_display_size)
		)
		for event, callback in patcher_callbacks:
			self.patcher.register_callback(event, callback)

	def remove_patch_callbacks(self):
		patcher_callbacks = (
			('speak', self.speak),
			('cancel_speech', self.cancel_speech),
			('display', self.display),
			('set_display', self.set_display_size)
		)
		for event, callback in patcher_callbacks:
			self.patcher.unregister_callback(event, callback)

	def speak(self, speechSequence, priority):
		self.transport.send(type="speak", sequence=speechSequence, priority=priority)

	def cancel_speech(self):
		self.transport.send(type="cancel")

	def display(self, cells):
		# Only send braille data when there are controlling machines with a braille display
		if self.has_braille_masters():
			self.transport.send(type="display", cells=cells)

	def has_braille_masters(self):
		return bool([i for i in self.master_display_sizes if i > 0])

class MasterSession(RemoteSession):

	def __init__(self, *args, **kwargs):
		super(MasterSession, self).__init__(*args, **kwargs)
		self.slaves = defaultdict(dict)
		self.patcher = nvda_patcher.NVDAMasterPatcher()
		self.patch_callbacks_added = False
		self.transport.callback_manager.register_callback('msg_speak', self.local_machine.speak)
		self.transport.callback_manager.register_callback('msg_cancel', self.local_machine.cancel_speech)
		self.transport.callback_manager.register_callback('msg_display', self.local_machine.display)
		self.transport.callback_manager.register_callback('msg_client_joined', self.handle_client_connected)
		self.transport.callback_manager.register_callback('msg_client_left', self.handle_client_disconnected)
		self.transport.callback_manager.register_callback('msg_channel_joined', self.handle_channel_joined)
		self.transport.callback_manager.register_callback('msg_send_braille_info', self.send_braille_info)

	def handle_channel_joined(self, channel=None, clients=None, origin=None, **kwargs):
		if clients is None:
			clients = []
		for client in clients:
			self.handle_client_connected(client)

	def handle_client_connected(self, client=None, **kwargs):
		self.patcher.patch()
		if not self.patch_callbacks_added:
			self.add_patch_callbacks()
			self.patch_callbacks_added = True
		self.send_braille_info()
		tones.beep(1000, 300)

	def handle_client_disconnected(self, client=None, **kwargs):
		self.patcher.unpatch()
		if self.patch_callbacks_added:
			self.remove_patch_callbacks()
			self.patch_callbacks_added = False
		tones.beep(108, 300)

	def send_braille_info(self, **kwargs):
		display = braille.handler.display
		self.transport.send(type="set_braille_info", name=display.name, numCells=display.numCells or braille.handler.displaySize)

	def braille_input(self, **kwargs):
		self.transport.send(type="braille_input", **kwargs)

	def add_patch_callbacks(self):
		patcher_callbacks = (('braille_input', self.braille_input), ('set_display', self.send_braille_info))
		for event, callback in patcher_callbacks:
			self.patcher.register_callback(event, callback)

	def remove_patch_callbacks(self):
		patcher_callbacks = (('braille_input', self.braille_input), ('set_display', self.send_braille_info))
		for event, callback in patcher_callbacks:
			self.patcher.unregister_callback(event, callback)
