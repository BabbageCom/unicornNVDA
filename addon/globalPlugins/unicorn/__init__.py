import os
import threading
import socket
import NVDAObjects
import braille
import ui
import addonHandler
import IAccessibleHandler
import speech.priorities
import globalVars
import shlobj
import uuid
import api
import ssl
import json
import versionInfo
import wx
import gui
from logHandler import log
from globalPluginHandler import GlobalPlugin
from config import conf
from typing import Callable

from .configSpec import configSpec
from . import beep_sequence
from .transport import RelayTransport, DVCTransport
from . import local_machine
from . import serializer
from .session import MasterSession, SlaveSession
from . import dialogs
from . import server
from . import bridge
from . import callback_manager
from . import unicorn

addonHandler.initTranslation()


REMOTE_SHELL_CLASSES = {
	'TscShellContainerClass',
	'CtxICADisp',
	'Transparent Windows Client'
}


def skipEventAndCall(handler):
	def wrapWithEventSkip(event):
		if event:
			event.Skip()
		return handler()
	return wrapWithEventSkip


class GlobalPlugin(GlobalPlugin):
	scriptCategory = "UnicornDVC"

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		if not unicorn.unicorn_lib_path():
			if not globalVars.appArgs.secure:
				wx.CallAfter(
					gui.messageBox,
					parent=gui.mainFrame,
					caption= _("Error"),
					message=_("UnicornDVC isn't available on your system."),
					style=wx.OK | wx.ICON_ERROR
				)
			raise RuntimeError("UnicornDVC not found")
		self.initializeConfig()
		gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(dialogs.UnicornPanel)
		self.local_machine = local_machine.LocalMachine()
		self.callback_manager = callback_manager.CallbackManager()
		self.slave_session = None
		self.master_session = None
		self.create_menu()
		self.master_transport = None
		self.slave_transport = None
		self.sd_server = None
		self.sd_relay = None
		self.sd_bridge = None
		if versionInfo.version_year < 2022:
			commonAppData = shlobj.SHGetFolderPath(0, shlobj.CSIDL_COMMON_APPDATA)
		else:
			commonAppData = shlobj.SHGetKnownFolderPath(shlobj.FolderId.PROGRAM_DATA)
		self.temp_location = os.path.join(commonAppData, 'temp')
		self.ipc_file = os.path.join(self.temp_location, 'unicorn.ipc')
		if globalVars.appArgs.secure:
			self.handle_secure_desktop()
		wx.CallLater(500, self.perform_autoconnect)
		self.sd_focused = False
		self.rs_focused = False
		if versionInfo.version_year >= 2023:
			braille.decide_enabled.register(self.local_machine.handle_decide_enabled)

	def initializeConfig(self) -> None:
		if "unicorn" not in conf:
			conf['unicorn'] = {}
		conf['unicorn'].spec.update(configSpec)

	def perform_autoconnect(self) -> None:
		if conf['unicorn']['autoConnectClient'] and unicorn.unicorn_client():
			self.connect_master()
		if conf['unicorn']['autoConnectServer']:
			self.connect_slave()

	def create_menu(self) -> None:
		self.menu = wx.Menu()
		self.connect_master_item = self.menu.Append(wx.ID_ANY, _("Connect client"))
		self.connect_master_item.Enable(unicorn.unicorn_client())
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, skipEventAndCall(self.connect_master), self.connect_master_item)
		self.disconnect_master_item = self.menu.Append(wx.ID_ANY, _("Disconnect client"))
		self.disconnect_master_item.Enable(False)
		gui.mainFrame.sysTrayIcon.Bind(
			wx.EVT_MENU,
			skipEventAndCall(self.disconnect_master), self.disconnect_master_item
		)
		self.connect_slave_item = self.menu.Append(wx.ID_ANY, _("Connect server"))
		gui.mainFrame.sysTrayIcon.Bind(
			wx.EVT_MENU,
			skipEventAndCall(self.connect_slave), self.connect_slave_item
		)
		self.disconnect_slave_item = self.menu.Append(wx.ID_ANY, _("Disconnect server"))
		self.disconnect_slave_item.Enable(False)
		gui.mainFrame.sysTrayIcon.Bind(
			wx.EVT_MENU,
			skipEventAndCall(self.disconnect_slave), self.disconnect_slave_item
		)
		self.mute_item = self.menu.Append(
			wx.ID_ANY,
			_("Mute remote"), _("Mute speech and sounds from the remote computer"), kind=wx.ITEM_CHECK
			)
		self.mute_item.Enable(False)
		gui.mainFrame.sysTrayIcon.Bind(
			wx.EVT_MENU,
			self.on_mute_item, self.mute_item
		)

		self.submenu_item = gui.mainFrame.sysTrayIcon.menu.Insert(2, wx.ID_ANY, _("UnicornDVC"), self.menu)

	def terminate(self) -> None:
		if versionInfo.version_year >= 2023:
			braille.decide_enabled.unregister(self.local_machine.handle_decide_enabled)
		self.disconnect()
		self.local_machine = None
		if self.submenu_item is not None:
			try:
				gui.mainFrame.sysTrayIcon.menu.Remove(self.submenu_item)
			except AttributeError:  # We can get this somehow from wx python when NVDA is shuttingdown, just ignore
				pass
			self.submenu_item.Destroy()
			self.submenu_item = None
		self.menu = None

		try:
			os.unlink(self.ipc_file)
		except Exception:
			pass

		if dialogs.UnicornPanel in gui.settingsDialogs.NVDASettingsDialog.categoryClasses:
			gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(dialogs.UnicornPanel)

	def connect_master(self) -> None:
		try:

			maxBytes = conf['unicorn']['maxBytes'] if conf['unicorn']['limitMessageSize'] else 10**9
			transport = DVCTransport(serializer=serializer.JSONSerializer(), connection_type=unicorn.CTYPE.CLIENT, maxBytes=maxBytes)
		except OSError as e:
			self.on_initialize_failed(e)
			return
		self.master_session = MasterSession(transport=transport, local_machine=self.local_machine)
		transport.callback_manager.register_callback('transport_connection_in_trial_mode', self.on_connected_in_trial_mode)
		transport.callback_manager.register_callback('transport_trial_expired', self.on_trial_expired)
		transport.callback_manager.register_callback('transport_connected', self.on_connected_as_master)
		transport.callback_manager.register_callback('transport_connection_failed', self.on_connected_as_master_failed)
		transport.callback_manager.register_callback('transport_closing', self.disconnecting_as_master)
		transport.callback_manager.register_callback('transport_disconnected', self.on_disconnected_as_master)
		transport.callback_manager.register_callback('msg_client_joined', lambda **kwargs: self.evaluate_remote_shell())
		transport.callback_manager.register_callback('update_plugin_dialog', self.on_connection_status_plugin_changed)		
		transport.callback_manager.register_callback('update_applib_dialog', self.on_connection_status_appllib_changed)		
		transport.callback_manager.register_callback('update_nvda_dialog', self.on_connection_status_nvda_changed)		
		dialogs.UnicornPanel.setIsServerSide(self, False)
		self.on_connection_status_nvda_changed(0)
		self.master_transport = transport
		self.master_transport.reconnector_thread.start()
		self.disconnect_master_item.Enable()
		self.connect_master_item.Enable(False)
  
	def connect_slave(self) -> None:
		try:
			maxBytes = conf['unicorn']['maxBytes'] if conf['unicorn']['limitMessageSize'] else 10 ** 9
			transport = DVCTransport(serializer=serializer.JSONSerializer(), connection_type=unicorn.CTYPE.SERVER, maxBytes=maxBytes)
		except OSError as e:
			self.on_initialize_failed(e)
			return
		self.slave_session = SlaveSession(transport=transport, local_machine=self.local_machine, is_secondary=bool(self.master_transport))
		self.slave_transport = transport
		self.slave_transport.callback_manager.register_callback('transport_connected', self.on_connected_as_slave)
		self.slave_transport.callback_manager.register_callback('msg_set_braille_info', self.send_braille_info_to_master)
		self.slave_transport.callback_manager.register_callback('update_applib_dialog', self.on_connection_status_appllib_changed)		
		self.slave_transport.callback_manager.register_callback('update_nvda_dialog', self.on_connection_status_nvda_changed)		
		self.on_connection_status_nvda_changed(0)
		dialogs.UnicornPanel.setIsServerSide(self, True)
		self.slave_transport.reconnector_thread.start()
		self.disconnect_slave_item.Enable()
		self.connect_slave_item.Enable(False)
		transport.callback_manager.register_callback('transport_connection_failed', self.on_connected_as_slave_failed)

	def on_connection_status_nvda_changed(self, winError):
		dialogs.UnicornPanel.connectionStatusFromNvdaChanged(self, winError)

	def on_connection_status_appllib_changed(self, winError):
		dialogs.UnicornPanel.connectionStatusFromApplibChanged(self, winError)

	def on_connection_status_plugin_changed(self, winError):
		dialogs.UnicornPanel.connectionStatusFromPluginChanged(self, winError)
    		
	def send_braille_info_to_master(self, *args, **kwargs) -> None:
		if self.master_session:
			self.master_session.send_braille_info(*args, **kwargs)

	def disconnect(self) -> None:
		if self.master_transport is not None:
			self.disconnect_master()
		if self.slave_transport is not None:
			self.disconnect_slave()

	def disconnect_master(self) -> None:
		self.callback_manager.call_callbacks('transport_disconnect', connection_type = unicorn.CTYPE.CLIENT)
		self.master_transport.close()
		self.master_transport = None
		self.master_session = None
		beep_sequence.beep_sequence_async((880, 60), (440, 60))
		self.disconnect_master_item.Enable(False)
		self.connect_master_item.Enable()

	def disconnecting_as_master(self) -> None:
		if self.menu:
			self.connect_master_item.Enable()
			self.disconnect_master_item.Enable(False)
			self.mute_item.Check(False)
			self.mute_item.Enable(False)
		if self.local_machine:
			self.local_machine.is_muted = False
		self.sending_keys = False

	def disconnect_slave(self) -> None:
		self.callback_manager.call_callbacks('transport_disconnect', connection_type = unicorn.CTYPE.SERVER)
		self.slave_transport.close()
		self.slave_transport = None
		self.slave_session = None
		beep_sequence.beep_sequence_async((660, 60), (330, 60))
		self.disconnect_slave_item.Enable(False)
		self.connect_slave_item.Enable()

	def on_mute_item(self, evt) -> None:
		evt.Skip()
		self.local_machine.is_muted = self.mute_item.IsChecked()

	def script_toggle_remote_mute(self, gesture) -> None:
		self.local_machine.is_muted = not self.local_machine.is_muted
		self.mute_item.Check(self.local_machine.is_muted)
	script_toggle_remote_mute.__doc__ = _("""Mute or unmute the speech coming from the remote computer""")

	def on_connected_as_master(self) -> None:
		self.mute_item.Enable(True)
		self.callback_manager.call_callbacks('transport_connect', connection_type= unicorn.CTYPE.CLIENT, transport=self.master_transport)
		self.evaluate_remote_shell()
		ui.message(_("Connected in client mode!"), speechPriority=speech.priorities.Spri.NOW)
		beep_sequence.beep_sequence_async((440, 60), (660, 60))

	def on_disconnected_as_master(self) -> None:
		# Translators: Presented when connection to a remote computer was interupted.
		ui.message(_("Connection as client interrupted"), speechPriority=speech.priorities.Spri.NOW)

	def on_connected_as_slave(self) -> None:
		log.info("Connected DVC in server mode")
		self.callback_manager.call_callbacks('transport_connect', connection_type = unicorn.CTYPE.SERVER, transport=self.slave_transport)
		ui.message(_("Connected in server mode!"), speechPriority=speech.priorities.Spri.NOW)

	def isRemoteShell(self, fg, focus) -> bool:
		if fg.windowClassName in REMOTE_SHELL_CLASSES:
			return True
		if focus.windowClassName in REMOTE_SHELL_CLASSES:
			return True
		if (focus.appModule.appName == 'vmware-view' and (focus.windowClassName.startswith("ATL") or focus.windowClassName.startswith("VMware.Horizon.Client.Sdk:RemoteWindow"))):
			return True

		return False

	def evaluate_remote_shell(self) -> None:
		focus = api.getFocusObject()
		fg = api.getForegroundObject()
		if self.isRemoteShell(fg, focus):
			self.rs_focused = True
			wx.CallAfter(self.enter_remote_shell)
		elif self.rs_focused and not self.isRemoteShell(fg, focus):
			self.rs_focused = False
			self.leave_remote_shell()

	def on_initialize_failed(self, e: Exception) -> None:
		# Translators: Title of the connection error dialog.
		wx.CallAfter(
			gui.messageBox,
			parent=gui.mainFrame,
			caption= _("Error Initializing"),
			# Translators: Message shown when cannot connect to the remote computer.
			message=_("Can't initialize UnicornDVC to create a virtual channel. Please make sure that you have a valid license.\nInternal error: {error}").format(error=e.strerror),
			style=wx.OK | wx.ICON_WARNING
		)

	def on_connected_as_master_failed(self) -> None:
		self.disconnect_master_item.Enable(False)
		self.connect_master_item.Enable()
		if self.master_transport.successful_connects == 0:
			self.disconnect_master()
			gui.messageBox(
				parent=gui.mainFrame,
				caption=_("Error Connecting"),
				# Translators: Message shown when cannot connect to the remote computer.
				message=_("Unable to connect to the virtual channel. Please make sure that your client is set up correctly"),
				style=wx.OK | wx.ICON_WARNING
			)

	def on_connected_in_trial_mode(self) -> None:
		if globalVars.appArgs.secure:
			return
		# Translators: Title of the trial dialog.
		gui.messageBox(
			parent=gui.mainFrame,
			caption=_("License Warning"),
			# Translators: Message shown when running in trial mode.
			message=_("UnicornDVC is running in trial mode. If this message is unexpected, please check whether you have a valid license."),
			style=wx.OK | wx.ICON_WARNING
		)

	def on_trial_expired(self) -> None:
		# Translators: Title of the trial dialog.
		gui.messageBox(
			parent=gui.mainFrame,
			# Translators: Title of the trial expireddialog.
			caption=_("Trial Expired"),
			# Translators: Message shown when trial is expired.
			message=_("Your 10 minutes trial of UnicornDVC has expired."),
			style=wx.OK | wx.ICON_WARNING
		)

	def on_connected_as_slave_failed(self) -> None:
		if self.slave_transport.successful_connects == 0:
			self.disconnect_slave()
			gui.messageBox(
				parent=gui.mainFrame,
				caption=_("Error Connecting"),
				# Translators: Message shown when cannot connect to the remote computer.
				message=_("Unable to connect to the virtual channel. Please make sure that you are in a remote session and that your client is set up correctly"),
				style=wx.OK | wx.ICON_WARNING
			)

	def set_receiving_braille(self, state: bool) -> None:
		if state and self.master_session and self.master_session.patch_callbacks_added and braille.handler.enabled:
			self.master_session.patcher.patch_braille_input()
			if versionInfo.version_year < 2023:
				braille.handler.enabled = False
			if braille.handler._cursorBlinkTimer:
				braille.handler._cursorBlinkTimer.Stop()
				braille.handler._cursorBlinkTimer = None
			if braille.handler.buffer is braille.handler.messageBuffer:
				braille.handler.buffer.clear()
				braille.handler.buffer = braille.handler.mainBuffer
				if braille.handler._messageCallLater:
					braille.handler._messageCallLater.Stop()
					braille.handler._messageCallLater = None
			self.local_machine.receiving_braille = True
		elif self.master_session and not state:
			self.master_session.patcher.unpatch_braille_input()
			if versionInfo.version_year < 2023:
				braille.handler.enabled = bool(braille.handler.displaySize)
			self.local_machine.receiving_braille=False

	def event_gainFocus(self, obj: NVDAObjects.NVDAObject, nextHandler: Callable) -> None:
		if isinstance(obj, IAccessibleHandler.SecureDesktopNVDAObject):
			self.sd_focused = True
			self.enter_secure_desktop()
		elif self.sd_focused and not isinstance(obj, IAccessibleHandler.SecureDesktopNVDAObject):
			#event_leaveFocus won't work for some reason
			self.sd_focused = False
			self.leave_secure_desktop()
		self.evaluate_remote_shell()
		nextHandler()

	def enter_secure_desktop(self) -> None:
		"""function ran when entering a secure desktop."""
		if self.slave_transport is None:
			return
		if not os.path.exists(self.temp_location):
			os.makedirs(self.temp_location)
		channel = str(uuid.uuid4())
		self.sd_server = server.Server(port=0, password=channel, bind_host='127.0.0.1')
		port = self.sd_server.server_socket.getsockname()[1]
		server_thread = threading.Thread(target=self.sd_server.run)
		server_thread.daemon = True
		server_thread.start()
		self.sd_relay = RelayTransport(address=('127.0.0.1', port), serializer=serializer.JSONSerializer(), channel=channel)
		self.sd_relay.callback_manager.register_callback('msg_client_joined', self.sd_on_master_display_change)
		self.slave_transport.callback_manager.register_callback('msg_set_braille_info', self.sd_on_master_display_change)
		self.sd_bridge = bridge.BridgeTransport(self.slave_transport, self.sd_relay)
		relay_thread = threading.Thread(target=self.sd_relay.run)
		relay_thread.daemon = True
		relay_thread.start()
		data = [port, channel]
		with open(self.ipc_file, 'w') as fp:
			json.dump(data, fp)

	def leave_secure_desktop(self) -> None:
		if self.sd_server is None:
			return #Nothing to do
		self.sd_bridge.disconnect()
		self.sd_bridge = None
		self.sd_server.close()
		self.sd_server = None
		self.sd_relay.close()
		self.sd_relay = None
		self.slave_transport.callback_manager.unregister_callback('msg_set_braille_info', self.sd_on_master_display_change)
		self.slave_session.set_display_size()

	def enter_remote_shell(self) -> None:
		if self.master_transport is None or not self.rs_focused:
			return
		self.set_receiving_braille(True)

	def leave_remote_shell(self) -> None:
		if not conf['unicorn']['alwaysReceiveRemoteBraille']: 
			self.set_receiving_braille(False)

	def sd_on_master_display_change(self, **kwargs) -> None:
		self.sd_relay.send(type='set_display_size', sizes=self.slave_session.master_display_sizes)

	def connect_slave_relay(self, address, key) -> None:
		transport = RelayTransport(serializer=serializer.JSONSerializer(), address=address, channel=key, connection_type = unicorn.CTYPE.SERVER)
		self.slave_session = SlaveSession(transport=transport, local_machine=self.local_machine)
		self.slave_transport = transport
		self.slave_transport.callback_manager.register_callback('transport_connected', self.on_connected_as_slave)
		self.slave_transport.reconnector_thread.start()
		self.disconnect_slave_item.Enable()
		self.connect_slave_item.Enable(False)

	def handle_secure_desktop(self) -> None:
		try:
			with open(self.ipc_file) as fp:
				data = json.load(fp)
			os.unlink(self.ipc_file)
			port, channel = data
			test_socket=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			test_socket=ssl.wrap_socket(test_socket)
			test_socket.connect(('127.0.0.1', port))
			test_socket.close()
			self.connect_as_slave(('127.0.0.1', port), channel)
		except:
			pass

	def is_connected(self) -> bool:
		connector = self.slave_transport or self.master_transport
		if connector is not None:
			return connector.connected
		return False
