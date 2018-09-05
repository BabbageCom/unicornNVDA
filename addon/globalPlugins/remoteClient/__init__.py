REMOTE_KEY = "kb:f11"
REMOTE_SHELL_CLASSES={u'TscShellContainerClass', u'CtxICADisp'}
import os
import sys
import json
import threading
import time
import socket
from globalPluginHandler import GlobalPlugin
import logging
logger = logging.getLogger(__name__)
import Queue
import select
import wx
from config import conf as nvda_conf,isInstalledCopy
import configuration
import gui
import beep_sequence
import speech
from transport import RelayTransport,DVCTransport
import braille
import local_machine
import serializer
from session import MasterSession, SlaveSession
import url_handler
import time
import ui
import addonHandler
addonHandler.initTranslation()
import keyboard_hook
import ctypes.wintypes as ctypes
import win32con
logging.getLogger("keyboard_hook").addHandler(logging.StreamHandler(sys.stdout))
from logHandler import log
import dialogs
import IAccessibleHandler
import tones
import globalVars
import shlobj
import uuid
import server
import bridge
from socket_utils import SERVER_PORT, address_to_hostport, hostport_to_address
import api
import ssl
import callback_manager
import installer
import unicorn

class GlobalPlugin(GlobalPlugin):
	scriptCategory = _("NVDA Remote")

	def __init__(self, *args, **kwargs):
		super(GlobalPlugin, self).__init__(*args, **kwargs)
		self.local_machine = local_machine.LocalMachine()
		self.callback_manager = callback_manager.CallbackManager()
		self.slave_session = None
		self.master_session = None
		self.create_menu()
		self.connecting = False
		self.url_handler_window = url_handler.URLHandlerWindow(callback=self.verify_connect)
		url_handler.register_url_handler()
		self.master_transport = None
		self.slave_transport = None
		self._secondary_started_server = False
		self.server = None
		self.hook_thread = None
		self.sending_keys = False
		self.key_modified = False
		self.sd_server = None
		self.sd_relay = None
		self.sd_bridge = None
		cs = configuration.get_config()['controlserver']
		self.temp_location = os.path.join(shlobj.SHGetFolderPath(0, shlobj.CSIDL_COMMON_APPDATA), 'temp')
		self.ipc_file = os.path.join(self.temp_location, 'remote.ipc')
		if globalVars.appArgs.secure:
			self.handle_secure_desktop()
		if cs['autoconnect'] and not self.master_session and not self.slave_session:
			wx.CallLater(50,self.perform_autoconnect)
		self.sd_focused = False
		self.rs_focused = False

	def perform_autoconnect(self):
		cs = configuration.get_config()['controlserver']
		channel = cs['key']
		if cs['self_hosted']:
			port = cs['port']
			address = ('localhost',port)
			self.start_control_server(port, channel)
		else:
			address = address_to_hostport(cs['host'])
		if cs['connection_type']==0:
			self.connect_as_dvc_slave() if cs['dvc'] else self.connect_as_slave(address, channel)
		else:
			self.connect_as_dvc_master() if cs['dvc'] else self.connect_as_master(address, channel)

	def create_menu(self):
		self.menu = wx.Menu()
		tools_menu = gui.mainFrame.sysTrayIcon.toolsMenu
		# Translators: Item in NVDA Remote submenu to connect to a remote computer.
		self.connect_item = self.menu.Append(wx.ID_ANY, _("Connect..."), _("Remotely connect to another computer running NVDA Remote Access"))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.do_connect, self.connect_item)
		# Translators: Item in NVDA Remote submenu to disconnect from a remote computer.
		self.disconnect_item = self.menu.Append(wx.ID_ANY, _("Disconnect"), _("Disconnect from another computer running NVDA Remote Access"))
		self.disconnect_item.Enable(False)
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.on_disconnect_item, self.disconnect_item)
		# Translators: Item in NVDA Remote submenu to connect to a secondary remote computer.
		self.connect_secondary_item = self.menu.Append(wx.ID_ANY, _("Connect second session..."), _("Connect to a second computer running NVDA Remote Access"))
		self.connect_secondary_item.Enable(False)
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.do_connect_secondary, self.connect_secondary_item)
		# Translators: Item in NVDA Remote submenu to disconnect from a secondary remote computer.
		self.disconnect_secondary_item = self.menu.Append(wx.ID_ANY, _("Disconnect second session"), _("Disconnect from a second computer running NVDA Remote Access"))
		self.disconnect_secondary_item.Enable(False)
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.on_disconnect_secondary_item, self.disconnect_secondary_item)
		# Translators: Menu item in NvDA Remote submenu to mute speech and sounds from the remote computer.
		self.mute_item = self.menu.Append(wx.ID_ANY, _("Mute remote"), _("Mute speech and sounds from the remote computer"), kind=wx.ITEM_CHECK)
		self.mute_item.Enable(False)
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.on_mute_item, self.mute_item)
		# Translators: Menu item in NVDA Remote submenu to push clipboard content to the remote computer.
		self.push_clipboard_item = self.menu.Append(wx.ID_ANY, _("&Push clipboard"), _("Push the clipboard to the other machine"))
		self.push_clipboard_item.Enable(False)
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.on_push_clipboard_item, self.push_clipboard_item)
		# Translators: Menu item in NVDA Remote submenu to copy a link to the current session.
		self.copy_link_item = self.menu.Append(wx.ID_ANY, _("Copy &link"), _("Copy a link to the remote session"))
		self.copy_link_item.Enable(False)
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.on_copy_link_item, self.copy_link_item)
		# Translators: Menu item in NvDA Remote submenu to open add-on options.
		self.options_item = self.menu.Append(wx.ID_ANY, _("&Options..."), _("Options"))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.on_options_item, self.options_item)
		# Translators: Menu item in NVDA Remote submenu to send Control+Alt+Delete to the remote computer.
		self.send_ctrl_alt_del_item = self.menu.Append(wx.ID_ANY, _("Send Ctrl+Alt+Del"), _("Send Ctrl+Alt+Del"))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.on_send_ctrl_alt_del, self.send_ctrl_alt_del_item)
		self.send_ctrl_alt_del_item.Enable(False)
		# Translators: Menu item in NVDA Remote submenu to provide a license key for UnicornDVC.
		self.manage_unicorn_license_item = self.menu.Append(wx.ID_ANY, _("Manage Unicorn License..."), _("Activate or deactivate UnicornDVC"))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.on_manage_unicorn_license, self.manage_unicorn_license_item)
		self.manage_unicorn_license_item.Enable(unicorn.unicorn_client())
		# Translators: Label of menu in NVDA tools menu.
		self.remote_item=tools_menu.AppendSubMenu(self.menu, _("R&emote"), _("NVDA Remote Access"))

	def terminate(self):
		self.disconnect()
		self.local_machine = None
		self.menu.Remove(self.connect_item.Id)
		self.connect_item.Destroy()
		self.connect_item=None
		self.menu.Remove(self.disconnect_item.Id)
		self.disconnect_item.Destroy()
		self.disconnect_item=None
		self.menu.RemoveItem(self.connect_secondary_item.Id)
		self.connect_secondary_item.Destroy()
		self.connect_secondary_item=None
		self.menu.RemoveItem(self.disconnect_secondary_item.Id)
		self.disconnect_secondary_item.Destroy()
		self.disconnect_secondary_item=None
		self.menu.Remove(self.mute_item.Id)
		self.mute_item.Destroy()
		self.mute_item=None
		self.menu.Remove(self.push_clipboard_item.Id)
		self.push_clipboard_item.Destroy()
		self.push_clipboard_item=None
		self.menu.Remove(self.copy_link_item.Id)
		self.copy_link_item.Destroy()
		self.copy_link_item = None
		self.menu.Remove(self.options_item.Id)
		self.options_item.Destroy()
		self.options_item=None
		self.menu.Remove(self.send_ctrl_alt_del_item.Id)
		self.send_ctrl_alt_del_item.Destroy()
		self.send_ctrl_alt_del_item=None
		self.menu.RemoveItem(		self.manage_unicorn_license_item)
		self.manage_unicorn_license_item.Destroy()
		self.manage_unicorn_license_item=None
		tools_menu = gui.mainFrame.sysTrayIcon.toolsMenu
		tools_menu.Remove(self.remote_item.Id)
		self.remote_item.Destroy()
		self.remote_item=None
		try:
			self.menu.Destroy()
		except (RuntimeError, AttributeError):
			pass
		try:
			os.unlink(self.ipc_file)
		except:
			pass
		self.menu=None
		if not isInstalledCopy():
			url_handler.unregister_url_handler()
		self.url_handler_window.destroy()
		self.url_handler_window=None

	def on_disconnect_item(self, evt):
		evt.Skip()
		self.disconnect()

	def on_disconnect_secondary_item(self, evt):
		evt.Skip()
		self.disconnect_secondary()

	def on_mute_item(self, evt):
		evt.Skip()
		self.local_machine.is_muted = self.mute_item.IsChecked()

	def script_toggle_remote_mute(self, gesture):
		self.local_machine.is_muted = not self.local_machine.is_muted
		self.mute_item.Check(self.local_machine.is_muted)
	script_toggle_remote_mute.__doc__ = _("""Mute or unmute the speech coming from the remote computer""")

	def on_push_clipboard_item(self, evt):
		connector = self.slave_transport or self.master_transport
		try:
			connector.send(type='set_clipboard_text', text=api.getClipData())
		except TypeError:
			log.exception("Unable to push clipboard")

	def script_push_clipboard(self, gesture):
		connector = self.slave_transport or self.master_transport
		if not getattr(connector,'connected',False):
			ui.message(_("Not connected."))
			return
		try:
			connector.send(type='set_clipboard_text', text=api.getClipData())
			ui.message(_("Clipboard pushed"))
		except TypeError:
			ui.message(_("Unable to push clipboard"))
	script_push_clipboard.__doc__ = _("Sends the contents of the clipboard to the remote machine")

	def on_copy_link_item(self, evt):
		session = self.master_session or self.slave_session
		url = session.get_connection_info().get_url_to_connect()
		api.copyToClip(unicode(url))

	def script_copy_link(self, gesture):
		self.on_copy_link_item(None)
		ui.message(_("Copied link"))
	script_copy_link.__doc__ = _("Copies a link to the remote session to the clipboard")

	def on_options_item(self, evt):
		evt.Skip()
		conf = configuration.get_config()
		# Translators: The title of the add-on options dialog.
		dlg = dialogs.OptionsDialog(gui.mainFrame, wx.ID_ANY, title=_("Options"))
		dlg.set_from_config(conf)
		def handle_dlg_complete(dlg_result):
			if dlg_result != wx.ID_OK:
				return
			dlg.write_to_config(conf)
		gui.runScriptModalDialog(dlg, callback=handle_dlg_complete)

	def on_send_ctrl_alt_del(self, evt):
		self.master_transport.send('send_SAS')

	def on_manage_unicorn_license(self, evt):
		# Translators: The title of the Manage UnicornDVC license dialog.
		dlg = dialogs.UnicornLicenseDialog(gui.mainFrame, wx.ID_ANY, title=_("Manage UnicornDVC License"))
		gui.runScriptModalDialog(dlg)

	def disconnect(self):
		if self.master_transport is None and self.slave_transport is None:
			return
		if self.server is not None:
			self.server.close()
			self.server = None
			self._secondary_started_server = False
		if self.master_transport is not None:
			self.disconnect_as_master()
		if self.slave_transport is not None:
			self.disconnect_as_slave()
		beep_sequence.beep_sequence_async((660, 60), (440, 60))
		self.disconnect_item.Enable(False)
		self.connect_item.Enable(True)
		self.disconnect_secondary_item.Enable(False)
		self.connect_secondary_item.Enable(False)
		self.push_clipboard_item.Enable(False)
		self.copy_link_item.Enable(False)

	def disconnect_as_master(self):
		self.callback_manager.call_callbacks('transport_disconnect', connection_type='master')
		self.master_transport.close()
		self.master_transport = None
		self.master_session = None

	def disconnecting_as_master(self):
		if self.menu:
			self.connect_item.Enable(True)
			self.disconnect_item.Enable(False)
			self.mute_item.Check(False)
			self.mute_item.Enable(False)
			self.push_clipboard_item.Enable(False)
			self.copy_link_item.Enable(False)
			self.send_ctrl_alt_del_item.Enable(False)
		if self.local_machine:
			self.local_machine.is_muted = False
		self.sending_keys = False
		if self.hook_thread is not None:
			ctypes.windll.user32.PostThreadMessageW(self.hook_thread.ident, win32con.WM_QUIT, 0, 0)
			self.hook_thread.join()
			self.hook_thread = None
			self.removeGestureBinding(REMOTE_KEY)
		self.key_modified = False

	def disconnect_as_slave(self):
		self.callback_manager.call_callbacks('transport_disconnect', connection_type='slave')
		self.slave_transport.close()
		self.slave_transport = None
		self.slave_session = None

	def disconnect_secondary(self):
		if self.slave_transport is None:
			return
		if self.server is not None and self._secondary_started_server:
			self.server.close()
			self.server = None
			self._secondary_started_server = False
		self.disconnect_as_slave()
		beep_sequence.beep_sequence_async((880, 100), 50, (660, 100), 50, (550, 100))
		self.disconnect_secondary_item.Enable(False)
		self.connect_secondary_item.Enable(bool(self.master_transport))

	def on_connected_as_master_failed(self):
		if self.master_transport.successful_connects == 0:
			self.disconnect()
			# Translators: Title of the connection error dialog.
			gui.messageBox(parent=gui.mainFrame, caption=_("Error Connecting"),
			# Translators: Message shown when cannot connect to the remote computer.
			message=_("Unable to connect to the remote computer"), style=wx.OK | wx.ICON_WARNING)

	def script_disconnect(self, gesture):
		if self.master_transport is None and self.slave_transport is None:
			ui.message(_("Not connected."))
			return
		self.disconnect()
	script_disconnect.__doc__ = _("""Disconnect a remote session""")

	def do_connect(self, evt):
		evt.Skip()
		last_cons = configuration.get_config()['connections']['last_connected']
		last = ''
		if last_cons:
			last = last_cons[-1]
		# Translators: Title of the connect dialog.
		dlg = dialogs.DirectConnectDialog(parent=gui.mainFrame, id=wx.ID_ANY, title=_("Connect"))
		dlg.panel.host.SetValue(last)
		dlg.panel.host.SelectAll()
		def handle_dlg_complete(dlg_result):
			if dlg_result != wx.ID_OK:
				return
			if dlg.client_or_server.GetSelection() != 2:
				channel = dlg.panel.key.GetValue()
			if dlg.client_or_server.GetSelection() == 0: #client
				server_addr = dlg.panel.host.GetValue()
				server_addr, port = address_to_hostport(server_addr)
				if dlg.connection_type.GetSelection() == 0:
					self.connect_as_master((server_addr, port), channel)
				else:
					self.connect_as_slave((server_addr, port), channel)
			elif dlg.client_or_server.GetSelection() == 1: #We want a server
				self.start_control_server(int(dlg.panel.port.GetValue()), channel)
				if dlg.connection_type.GetSelection() == 0:
					self.connect_as_master(('127.0.0.1', int(dlg.panel.port.GetValue())), channel)
				else:
					self.connect_as_slave(('127.0.0.1', int(dlg.panel.port.GetValue())), channel)
			elif dlg.client_or_server.GetSelection() == 2:
				if dlg.connection_type.GetSelection() == 0:
					self.connect_as_dvc_master()
				else:
					self.connect_as_dvc_slave()
		gui.runScriptModalDialog(dlg, callback=handle_dlg_complete)

	def do_connect_secondary(self, evt):
		evt.Skip()
		# Translators: Title of the secondary connect dialog.
		dlg = dialogs.DirectConnectDialog(parent=gui.mainFrame, id=wx.ID_ANY, title=_("Connect Second Session"), allowMaster=False, allowServer=bool(not self.server))
		def handle_dlg_complete(dlg_result):
			if dlg_result != wx.ID_OK:
				return
			if dlg.client_or_server.GetSelection() != 2:
				channel = dlg.panel.key.GetValue()
			if dlg.client_or_server.GetSelection() == 0: #client
				server_addr = dlg.panel.host.GetValue()
				server_addr, port = address_to_hostport(server_addr)
				self.connect_secondary((server_addr, port), channel)
			elif dlg.client_or_server.GetSelection() == 1: #We want a server
				self.start_control_server(int(dlg.panel.port.GetValue()), channel)
				self._secondary_started_server = True
				self.connect_secondary(('127.0.0.1', int(dlg.panel.port.GetValue())), channel)
			elif dlg.client_or_server.GetSelection() == 2:
				self.connect_secondary_dvc()
		gui.runScriptModalDialog(dlg, callback=handle_dlg_complete)

	def on_connected_as_master(self):
		configuration.write_connection_to_config(self.master_transport.address)
		self.disconnect_item.Enable(True)
		self.connect_item.Enable(False)
		self.mute_item.Enable(True)
		self.push_clipboard_item.Enable(True)
		self.copy_link_item.Enable(True)
		self.send_ctrl_alt_del_item.Enable(True)
		self.connect_secondary_item.Enable(bool(not self.slave_transport))
		self.disconnect_secondary_item.Enable(bool(self.slave_transport))
		self.hook_thread = threading.Thread(target=self.hook)
		self.hook_thread.daemon = True
		self.hook_thread.start()
		self.bindGesture(REMOTE_KEY, "sendKeys")
		self.callback_manager.call_callbacks('transport_connect', connection_type='master', transport=self.master_transport)
		# Translators: Presented when connected to the remote computer.
		ui.message(_("Connected!"))
		beep_sequence.beep_sequence_async((440, 60), (660, 60))

	def on_disconnected_as_master(self):
		# Translators: Presented when connection to a remote computer was interupted.
		ui.message(_("Connection interrupted"))

	def connect_as_master(self, address, key):
		transport = RelayTransport(address=address, serializer=serializer.JSONSerializer(), channel=key, connection_type='master')
		self.master_session = MasterSession(transport=transport, local_machine=self.local_machine)
		transport.callback_manager.register_callback('transport_connected', self.on_connected_as_master)
		transport.callback_manager.register_callback('transport_connection_failed', self.on_connected_as_master_failed)
		transport.callback_manager.register_callback('transport_closing', self.disconnecting_as_master)
		transport.callback_manager.register_callback('transport_disconnected', self.on_disconnected_as_master)
		self.master_transport = transport
		self.master_transport.reconnector_thread.start()

	def connect_as_slave(self, address, key):
		if not nvda_conf['keyboard']['handleInjectedKeys'] and gui.messageBox(
		# Translators: A message to warn the user that handle keys from other applications should be on.
		message=_("The option to handle keys from other applications is disabled in your NVDA keyboard settings. In order to allow the keyboard of this machine to be controlled, this option should be enabled. Would you like to do this now?"),
		# Translators: The title of the warning dialog displayed when handle keys from other applications is disabled.
		caption=_("Warning"),style=wx.YES|wx.NO|wx.ICON_WARNING)==wx.YES:
			nvda_conf['keyboard']['handleInjectedKeys']=True
		transport = RelayTransport(serializer=serializer.JSONSerializer(), address=address, channel=key, connection_type='slave')
		self.slave_session = SlaveSession(transport=transport, local_machine=self.local_machine)
		self.slave_transport = transport
		self.slave_transport.callback_manager.register_callback('transport_connected', self.on_connected_as_slave)
		self.slave_transport.reconnector_thread.start()
		self.disconnect_item.Enable(True)
		self.connect_item.Enable(False)

	def on_connected_as_slave(self):
		log.info("Control connector connected")
		beep_sequence.beep_sequence_async((720, 100), 50, (720, 100), 50, (720, 100))
		self.callback_manager.call_callbacks('transport_connect', connection_type='slave', transport=self.slave_transport)
		# Translators: Presented in direct (client to server) remote connection when the controlled computer is ready.
		speech.speakMessage(_("Connected to control server"))
		self.push_clipboard_item.Enable(True)
		self.copy_link_item.Enable(True)
		configuration.write_connection_to_config(self.slave_transport.address)

	def on_connected_as_dvc_slave(self):
		log.info("Control connector connected")
		self.callback_manager.call_callbacks('transport_connect', connection_type='slave', transport=self.slave_transport)
		self.push_clipboard_item.Enable(True)

	def connect_secondary(self, address, key):
		transport = RelayTransport(serializer=serializer.JSONSerializer(), address=address, channel=key, connection_type='slave')
		self.slave_session = SlaveSession(transport=transport, local_machine=self.local_machine, is_secondary=True)
		self.slave_transport = transport
		self.slave_transport.callback_manager.register_callback('transport_connected', self.on_secondary_connected)
		self.slave_transport.callback_manager.register_callback('msg_set_braille_info', self.master_session.send_braille_info)
		self.slave_transport.reconnector_thread.start()
		self.disconnect_secondary_item.Enable(True)
		self.connect_secondary_item.Enable(False)

	def connect_secondary_dvc(self):
		try:
			transport = DVCTransport(serializer=serializer.JSONSerializer(), connection_type='slave')
		except WindowsError as e:
			self.on_dvc_initialize_failed(e)
			return
		self.slave_session = SlaveSession(transport=transport, local_machine=self.local_machine, is_secondary=True)
		self.slave_transport = transport
		self.slave_transport.callback_manager.register_callback('transport_connected', self.on_secondary_connected)
		self.slave_transport.callback_manager.register_callback('msg_set_braille_info', self.master_session.send_braille_info)
		self.slave_transport.reconnector_thread.start()
		self.disconnect_secondary_item.Enable(True)
		self.connect_secondary_item.Enable(False)
		transport.callback_manager.register_callback('transport_connection_failed', self.on_connected_as_secondary_dvc_failed)

	def on_secondary_connected(self):
		log.info("Secondary connection successful")
		beep_sequence.beep_sequence_async((550, 100), 50, (660, 100), 50, (880, 100))
		# Translators: Presented in remote connection when the secondary session is ready.
		speech.speakMessage(_("Secondary session connected"))

	def start_control_server(self, server_port, channel):
		self.server = server.Server(server_port, channel)
		server_thread = threading.Thread(target=self.server.run)
		server_thread.daemon = True
		server_thread.start()

	def evaluate_remote_shell(self):
		focus = api.getFocusObject()
		fg = api.getForegroundObject()
		if fg.windowClassName in REMOTE_SHELL_CLASSES or focus.windowClassName in REMOTE_SHELL_CLASSES or (focus.appModule.appName==u'vmware-view' and focus.windowClassName.startswith("ATL")):
			self.rs_focused = True
			wx.CallAfter(self.enter_remote_shell)
		elif self.rs_focused and fg.windowClassName not in REMOTE_SHELL_CLASSES and focus.windowClassName not in REMOTE_SHELL_CLASSES and not (focus.appModule.appName==u'vmware-view' and focus.windowClassName.startswith("ATL")):
			self.rs_focused = False
			self.leave_remote_shell()

	def on_connected_as_dvc_master(self):
		self.mute_item.Enable(True)
		self.push_clipboard_item.Enable(True)
		self.send_ctrl_alt_del_item.Enable(True)
		self.callback_manager.call_callbacks('transport_connect', connection_type='master', transport=self.master_transport)
		self.evaluate_remote_shell()
		# Translators: Presented when connected to the remote computer.
		ui.message(_("Connected!"))
		beep_sequence.beep_sequence_async((440, 60), (660, 60))

	def connect_as_dvc_master(self):
		try:
			transport = DVCTransport(serializer=serializer.JSONSerializer(), connection_type='master')
		except WindowsError as e:
			self.on_dvc_initialize_failed(e)
			return
		self.master_session = MasterSession(transport=transport, local_machine=self.local_machine)
		transport.callback_manager.register_callback('transport_connected', self.on_connected_as_dvc_master)
		transport.callback_manager.register_callback('transport_connection_failed', self.on_connected_as_dvc_master_failed)
		transport.callback_manager.register_callback('transport_connection_in_trial_mode', self.on_connected_in_trial_mode)
		transport.callback_manager.register_callback('transport_closing', self.disconnecting_as_master)
		transport.callback_manager.register_callback('transport_disconnected', self.on_disconnected_as_master)
		transport.callback_manager.register_callback('msg_client_joined', lambda **kwargs: self.evaluate_remote_shell())
		self.master_transport = transport
		self.master_transport.reconnector_thread.start()
		self.disconnect_item.Enable(True)
		self.connect_item.Enable(False)
		self.connect_secondary_item.Enable(bool(not self.slave_transport))
		self.disconnect_secondary_item.Enable(bool(self.slave_transport))

	def connect_as_dvc_slave(self):
		try:
			transport = DVCTransport(serializer=serializer.JSONSerializer(), connection_type='slave')
		except WindowsError as e:
			self.on_dvc_initialize_failed(e)
			return
		self.slave_session = SlaveSession(transport=transport, local_machine=self.local_machine)
		self.slave_transport = transport
		self.slave_transport.callback_manager.register_callback('transport_connected', self.on_connected_as_dvc_slave)
		self.slave_transport.reconnector_thread.start()
		self.disconnect_item.Enable(True)
		self.connect_item.Enable(False)
		transport.callback_manager.register_callback('transport_connection_failed', self.on_connected_as_dvc_slave_failed)

	def on_dvc_initialize_failed(self, e):
		# Translators: Title of the connection error dialog.
		wx.CallAfter(gui.messageBox,parent=gui.mainFrame, caption=_("Error Initializing"),
		# Translators: Message shown when cannot connect to the remote computer.
		message=_("Can't initialize UnicornDVC to create a virtual channel. Please make sure that you have a valid license.\nInternal error: {error}").format(error=e.strerror), style=wx.OK | wx.ICON_WARNING)

	def on_connected_as_dvc_master_failed(self):
		self.disconnect_item.Enable(False)
		self.connect_item.Enable(True)
		if self.master_transport.successful_connects == 0:
			self.disconnect()
			# Translators: Title of the connection error dialog.
			gui.messageBox(parent=gui.mainFrame, caption=_("Error Connecting"),
			# Translators: Message shown when cannot connect to the remote computer.
			message=_("Unable to connect to the virtual channel. Please make sure that your client is set up correctly"), style=wx.OK | wx.ICON_WARNING)

	def on_connected_in_trial_mode(self):
		# Translators: Title of the trial dialog.
		gui.messageBox(parent=gui.mainFrame, caption=_("License Warning"),
		# Translators: Message shown when running in trial mode.
		message=_("UnicornDVC is running in trial mode. If this message is unexpected, please check whether you have a valid license."), style=wx.OK | wx.ICON_WARNING)

	def on_connected_as_dvc_slave_failed(self):
		if self.slave_transport.successful_connects == 0:
			self.disconnect()
			# Translators: Title of the connection error dialog.
			gui.messageBox(parent=gui.mainFrame, caption=_("Error Connecting"),
			# Translators: Message shown when cannot connect to the remote computer.
			message=_("Unable to connect to the virtual channel. Please make sure that you are in a remote session and that your client is set up correctly"), style=wx.OK | wx.ICON_WARNING)

	def on_connected_as_secondary_dvc_failed(self):
		if self.slave_transport.successful_connects == 0:
			self.disconnect_secondary()
			# Translators: Title of the connection error dialog.
			gui.messageBox(parent=gui.mainFrame, caption=_("Error Connecting"),
			# Translators: Message shown when cannot connect to the remote computer.
			message=_("Unable to connect to the virtual channel. Please make sure that your client is set up correctly"), style=wx.OK | wx.ICON_WARNING)

	def hook(self):
		log.debug("Hook thread start")
		keyhook = keyboard_hook.KeyboardHook()
		keyhook.register_callback(self.hook_callback)
		msg = ctypes.MSG()
		while ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0):
			pass
		log.debug("Hook thread end")
		keyhook.free()

	def hook_callback(self, **kwargs):
		#Prevent disabling sending keys if another key is held down
		if not self.sending_keys:
			return False
		if kwargs['vk_code'] != win32con.VK_F11:
			self.key_modified = kwargs['pressed']
		if kwargs['vk_code'] == win32con.VK_F11 and kwargs['pressed'] and not self.key_modified:
			self.sending_keys = False
			self.set_receiving_braille(False)
			# This is called from the hook thread and should be executed on the main thread.
			# Translators: Presented when keyboard control is back to the controlling computer.
			wx.CallAfter(ui.message, _("Controlling local machine."))
			return True #Don't pass it on
		self.master_transport.send(type="key", **kwargs)
		return True #Don't pass it on

	def script_sendKeys(self, gesture):
		# Translators: Presented when sending keyboard keys from the controlling computer to the controlled computer.
		ui.message(_("Controlling remote machine."))
		self.sending_keys = True
		self.set_receiving_braille(True)

	def set_receiving_braille(self, state):
		if state and self.master_session and self.master_session.patch_callbacks_added and braille.handler.enabled:
			self.master_session.patcher.patch_braille_input()
			braille.handler.enabled = False
			if braille.handler._cursorBlinkTimer:
				braille.handler._cursorBlinkTimer.Stop()
				braille.handler._cursorBlinkTimer=None
			if braille.handler.buffer is braille.handler.messageBuffer:
				braille.handler.buffer.clear()
				braille.handler.buffer = braille.handler.mainBuffer
				if braille.handler._messageCallLater:
					braille.handler._messageCallLater.Stop()
					braille.handler._messageCallLater = None
			self.local_machine.receiving_braille=True
		elif self.master_session and not state:
			self.master_session.patcher.unpatch_braille_input()
			braille.handler.enabled = bool(braille.handler.displaySize)
			self.local_machine.receiving_braille=False

	def event_gainFocus(self, obj, nextHandler):
		if isinstance(obj, IAccessibleHandler.SecureDesktopNVDAObject):
			self.sd_focused = True
			self.enter_secure_desktop()
		elif self.sd_focused and not isinstance(obj, IAccessibleHandler.SecureDesktopNVDAObject):
			#event_leaveFocus won't work for some reason
			self.sd_focused = False
			self.leave_secure_desktop()
		self.evaluate_remote_shell()
		nextHandler()

	def enter_secure_desktop(self):
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
		with open(self.ipc_file, 'wb') as fp:
			json.dump(data, fp)

	def leave_secure_desktop(self):
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

	def enter_remote_shell(self):
		if self.master_transport is None or not self.rs_focused:
			return
		self.set_receiving_braille(True)

	def leave_remote_shell(self):
		self.set_receiving_braille(False)

	def sd_on_master_display_change(self, **kwargs):
		self.sd_relay.send(type='set_display_size', sizes=self.slave_session.master_display_sizes)

	def handle_secure_desktop(self):
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

	def verify_connect(self, con_info):
		if self.is_connected() or self.connecting:
			gui.messageBox(_("NVDA Remote is already connected. Disconnect before opening a new connection."), _("NVDA Remote Already Connected"), wx.OK|wx.ICON_WARNING)
			return
		self.connecting = True
		server_addr = con_info.get_address()
		key = con_info.key
		if con_info.mode == 'master':
			message = _("Do you wish to control the machine on server {server} with key {key}?").format(server=server_addr, key=key)
		elif con_info.mode == 'slave':
			message = _("Do you wish to allow this machine to be controlled on server {server} with key {key}?").format(server=server_addr, key=key)
		if gui.messageBox(message, _("NVDA Remote Connection Request"), wx.YES|wx.NO|wx.NO_DEFAULT|wx.ICON_WARNING) != wx.YES:
			self.connecting = False
			return
		if con_info.mode == 'master':
			self.connect_as_master((con_info.hostname, con_info.port), key=key)
		elif con_info.mode == 'slave':
			self.connect_as_slave((con_info.hostname, con_info.port), key=key)
		self.connecting = False

	def is_connected(self):
		connector = self.slave_transport or self.master_transport
		if connector is not None:
			return connector.connected
		return False

	__gestures = {
		"kb:alt+NVDA+pageDown": "disconnect",
		"kb:control+shift+NVDA+c": "push_clipboard",
	}
