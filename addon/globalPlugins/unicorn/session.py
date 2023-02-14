import threading
import time
import speech
import speech.commands
import speech.priorities
import braille
from . import nvda_patcher, callbackCommandsDatabase
from collections import defaultdict
import tones
import synthDriverHandler
from logHandler import log
import os
import versionInfo
from . import local_machine
from . import transport
from typing import Dict, List
from . import unicorn
EXCLUDED_SPEECH_COMMANDS = ( speech.commands._CancellableSpeechCommand,)




class RemoteSession(object):

	def __init__(self, local_machine: local_machine.LocalMachine, transport: transport.Transport):
		self.local_machine = local_machine
		self.patcher = None
		self.transport = transport



class SlaveSession(RemoteSession):
	"""Session that runs on the slave and manages state."""

	def __init__(self, *args, is_secondary: bool = False, **kwargs):
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
		if versionInfo.version_year >= 2023:
			braille.filter_displaySize.register(self.local_machine.handle_filter_displaySize)

		self.transport.callback_manager.register_callback('msg_braille_input', self.local_machine.braille_input)
		self.transport.callback_manager.register_callback('msg_callbackCommandBounce', self.callbackCommandBounce)

	def callbackCommandBounce(self, compName: str, index: int, **kwargs ) -> None:
		# function that is used for the speech callbackCommands. It checks if the callbackcommand originated from this
		# computer and then searches for the saved function in the database
		if compName == callbackCommandsDatabase.compName:
			function = callbackCommandsDatabase.callBackDatabase.get(index)
			if function:
				function()
				del callbackCommandsDatabase.callBackDatabase[index]

	def handle_client_connected(self, client: Dict, **kwargs) -> None:
		self.patcher.patch()
		if not self.patch_callbacks_added:
			self.add_patch_callbacks()
			self.patch_callbacks_added = True
		(self.patcher.orig_beep or tones.beep)(1000, 300)
		if client['connection_type'] == unicorn.CTYPE.CLIENT: # 'master':
			self.masters[client['id']]['active'] = True

	def handle_channel_joined(self, channel=None, clients=None, origin=None, **kwargs) -> None:
		if clients is None:
			clients = []
		for client in clients:
			self.handle_client_connected(client)

	def handle_disconnected(self) -> None:
		self.masters.clear()

	def handle_transport_closing(self) -> None:
		self.patcher.unpatch()
		if self.patch_callbacks_added:
			self.remove_patch_callbacks()
			self.patch_callbacks_added = False

	def handle_client_disconnected(self, client: Dict, **kwargs) -> None:
		(self.patcher.orig_beep or tones.beep)(108, 300)
		if client['connection_type'] == unicorn.CTYPE.CLIENT:
			del self.masters[client['id']]
		if not self.masters:
			self.patcher.unpatch()

	def set_display_size(self, sizes=None, **kwargs) -> None:
		self.master_display_sizes = sizes if sizes else [info.get("braille_numCells", 0) for info in self.masters.values()]
		self.local_machine.set_braille_display_size(self.master_display_sizes)

	def handle_braille_info(self, origin: int, name: str = "", numCells: int = 0, **kwargs) -> None:
		if not self.masters.get(origin):
			return
		self.masters[origin]['braille_name'] = name
		self.masters[origin]['braille_numCells'] = numCells
		self.set_display_size()

	def add_patch_callbacks(self) -> None:
		patcher_callbacks = (
			('speak', self.speak),
			('cancel_speech', self.cancel_speech),
			('beep', self.beep),
			('wave', self.playWaveFile),
			('display', self.display),
			('set_display', self.set_display_size)
		)
		for event, callback in patcher_callbacks:
			self.patcher.register_callback(event, callback)

	def remove_patch_callbacks(self) -> None:
		patcher_callbacks = (
			('speak', self.speak),
			('cancel_speech', self.cancel_speech),
			('beep', self.beep),
			('wave', self.playWaveFile),
			('display', self.display),
			('set_display', self.set_display_size)
		)
		for event, callback in patcher_callbacks:
			self.patcher.unregister_callback(event, callback)

	def _filterUnsupportedSpeechCommands(self, speechSequence: speech.SpeechSequence) -> speech.SpeechSequence:
		return list([
			item for item in speechSequence
			if not isinstance(item, EXCLUDED_SPEECH_COMMANDS)
		])

	def speak(self, speechSequence: speech.SpeechSequence, priority: speech.priorities.Spri) -> None:
		self.transport.send(
			type="speak",
			sequence=self._filterUnsupportedSpeechCommands(speechSequence),
			priority=priority
		)

	def cancel_speech(self) -> None:
		self.transport.send(type="cancel")

	def beep(self, hz: float, length: int, left: int = 50, right: int = 50, isSpeechBeepCommand: bool = False) -> None:
		self.transport.send(type='tone', hz=hz, length=length, left=left, right=right, isSpeechBeepCommand=isSpeechBeepCommand)


	def playWaveFile(self, fileName: str, asynchronous: bool = True, isSpeechWaveFileCommand: bool = False) -> None:
		# 20220428 remove absolute path
		parts = fileName.rpartition('waves\\')
		fileName = parts[1]+parts[2]
		self.transport.send(type='wave', fileName=fileName, asynchronous=asynchronous, isSpeechWaveFileCommand=isSpeechWaveFileCommand)


	def display(self, cells: List[int]) -> None:
		log.debugWarning(f"sending to other braille display: {cells}")
		# Only send braille data when there are controlling machines with a braille display
		if self.has_braille_masters():
			log.debugWarning(f"no braille masters!")
			self.transport.send(type="display", cells=cells)

	def has_braille_masters(self) -> bool:
		return bool([i for i in self.master_display_sizes if i > 0])

class MasterSession(RemoteSession):

	def __init__(self, *args, **kwargs):
		super(MasterSession, self).__init__(*args, **kwargs)
		self.slaves = defaultdict(dict)
		self.patcher = nvda_patcher.NVDAMasterPatcher()
		self.patch_callbacks_added = False
		self.transport.callback_manager.register_callback('msg_speak', self.local_machine.speak)
		self.transport.callback_manager.register_callback('msg_cancel', self.local_machine.cancel_speech)
		self.transport.callback_manager.register_callback('msg_tone', self.local_machine.beep)
		self.transport.callback_manager.register_callback('msg_wave', self.local_machine.play_wave)
		self.transport.callback_manager.register_callback('msg_display', self.local_machine.display)
		self.transport.callback_manager.register_callback('msg_client_joined', self.handle_client_connected)
		self.transport.callback_manager.register_callback('msg_client_left', self.handle_client_disconnected)
		self.transport.callback_manager.register_callback('msg_channel_joined', self.handle_channel_joined)
		self.transport.callback_manager.register_callback('msg_send_braille_info', self.send_braille_info)




	def handle_channel_joined(self, channel=None, clients=None, origin=None, **kwargs) -> None:
		if clients is None:
			clients = []
		for client in clients:
			self.handle_client_connected(client)

	def handle_client_connected(self, client = Dict, **kwargs) -> None:
		self.patcher.patch()
		if not self.patch_callbacks_added:
			self.add_patch_callbacks()
			self.patch_callbacks_added = True
		self.send_braille_info()
		tones.beep(1000, 300)

	def handle_client_disconnected(self, client = Dict, **kwargs) -> None:
		self.patcher.unpatch()
		if self.patch_callbacks_added:
			self.remove_patch_callbacks()
			self.patch_callbacks_added = False
		tones.beep(108, 300)

	def send_braille_info(self, display=None, displaySize=None, **kwargs) -> None:
		if display is None:
			display = braille.handler.display
		if displaySize is None:
			displaySize = braille.handler.displaySize
		self.transport.send(type="set_braille_info", name=display.name, numCells=displaySize)

	def braille_input(self, **kwargs) -> None:
		self.transport.send(type="braille_input", **kwargs)

	def add_patch_callbacks(self) -> None:
		patcher_callbacks = (
			('braille_input', self.braille_input),
			('set_display', self.send_braille_info)
		)
		for event, callback in patcher_callbacks:
			self.patcher.register_callback(event, callback)

	def remove_patch_callbacks(self) -> None:
		patcher_callbacks = (
			('braille_input', self.braille_input),
			('set_display', self.send_braille_info)
		)
		for event, callback in patcher_callbacks:
			self.patcher.unregister_callback(event, callback)
