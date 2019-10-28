import sys
import os
import json
import random
import threading
import urllib
import wx
import gui
import serializer
import server
import transport
import socket_utils
from unicorn import *
from ctypes import byref, create_unicode_buffer, WinError
import watchdog
import addonHandler
addonHandler.initTranslation()

WX_VERSION = int(wx.version()[0])
WX_CENTER = wx.Center if WX_VERSION>=4 else wx.CENTER_ON_SCREEN

class OptionsDialog(wx.Dialog):

	def __init__(self, parent, id, title):
		super(OptionsDialog, self).__init__(parent, id, title=title)
		main_sizer = wx.BoxSizer(wx.VERTICAL)
		main_sizer_helper = gui.guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)
		# Translators: A checkbox in add-on options dialog to set whether remote server is started when NVDA starts.
		self.autoconnect = main_sizer_helper.addItem(wx.CheckBox(self, wx.ID_ANY, label=_("Auto-connect on startup")))
		self.autoconnect.Bind(wx.EVT_CHECKBOX, self.on_autoconnect)
		choices = [_("Allow this machine to be controlled"), _("Control another machine")]
		self.connection_type = main_sizer_helper.addItem(wx.RadioBox(self, wx.ID_ANY, choices=choices, style=wx.RA_VERTICAL))
		self.connection_type.SetSelection(0)
		self.connection_type.Enable(False)
		main_sizer_helper.addDialogDismissButtons(self.CreateButtonSizer(wx.OK | wx.CANCEL))
		self.Bind(wx.EVT_BUTTON, self.on_ok, id=wx.ID_OK)
		main_sizer.Add(main_sizer_helper.sizer, border = gui.guiHelper.BORDER_FOR_DIALOGS, flag=wx.ALL)
		main_sizer.Fit(self)
		self.SetSizer(main_sizer)
		self.Center(wx.BOTH | WX_CENTER)
		self.autoconnect.SetFocus()

	def on_autoconnect(self, evt):
		self.set_controls()

	def set_controls(self):
		clientState= bool(unicorn_client())
		self.connection_type.EnableItem(1,clientState)
		if not clientState:
			self.connection_type.SetSelection(0)

	def set_from_config(self, config):
		cs = config['controlserver']
		self_hosted = cs['self_hosted']
		dvc = cs['dvc']
		connection_type = cs['connection_type']
		self.autoconnect.SetValue(cs['autoconnect'])
		self.client_or_server.SetSelection(2 if dvc else int(self_hosted))
		self.connection_type.SetSelection(connection_type)
		self.host.SetValue(cs['host'])
		self.port.SetValue(str(cs['port']))
		self.key.SetValue(cs['key'])
		self.set_controls()

	def on_ok(self, evt):
		if self.autoconnect.GetValue():
			if self.client_or_server.GetSelection()==0 and (not self.host.GetValue() or not self.key.GetValue()):
				gui.messageBox(_("Both host and key must be set."), _("Error"), wx.OK | wx.ICON_ERROR)
			elif self.client_or_server.GetSelection()==1 and (not self.port.GetValue() or not self.key.GetValue()):
				gui.messageBox(_("Both port and key must be set."), _("Error"), wx.OK | wx.ICON_ERROR)
			else:
				evt.Skip()
		else:
			evt.Skip()

	def write_to_config(self, config):
		cs = config['controlserver']
		cs['autoconnect'] = self.autoconnect.GetValue()
		self_hosted = self.client_or_server.GetSelection()==1
		dvc = self.client_or_server.GetSelection()==2
		connection_type = self.connection_type.GetSelection()
		cs['self_hosted'] = self_hosted
		cs['dvc'] = dvc
		cs['connection_type'] = connection_type
		if not self_hosted:
			cs['host'] = self.host.GetValue()
		else:
			cs['port'] = int(self.port.GetValue())
		cs['key'] = self.key.GetValue()
		config.write()

class UnicornLicenseDialog(wx.Dialog):

	def __init__(self, parent, id, title):
		if not bool(unicorn_client()):
			wx.CallAfter(gui.messageBox,_("The UnicornDVC client is not available on your system. Managing a license is therefore not supported."), _("Error"), wx.OK | wx.ICON_ERROR)
			return
		# Create a temporary instance of the Unicorn object.
		try:
			self.handler = UnicornCallbackHandler()
			self.lib=Unicorn(CTYPE_CLIENT, self.handler)
		except AttributeError:
			wx.CallAfter(gui.messageBox,_("The UnicornDVC client available on your system is out of date. Managing a license is therefore not supported."), _("Error"), wx.OK | wx.ICON_ERROR)
			raise
		super(UnicornLicenseDialog, self).__init__(parent, id, title=title)
		self.isLicensed = self.lib.IsLicensed()
		if self.isLicensed:
			message = _("Your copy of UnicornDVC is properly licensed.\nChoose OK to deactivate the product, or Cancel to close this dialog.")
		else:
			message = _("Your copy of UnicornDVC doesn't seem to be licensed.\nEnter your license key in the respective field and choose OK to activate the product.\nAlternatively, press Cancel to close this dialog.")
		main_sizer = wx.BoxSizer(wx.VERTICAL)
		main_sizer.Add(wx.StaticText(self, label=message))
		main_sizer_helper = gui.guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)
		#Translators: The input field to enter the Unicorn license key
		self.key = main_sizer_helper.addLabeledControl(_("&License Key:"), wx.TextCtrl)
		self.key.Enabled=not self.isLicensed
		main_sizer_helper.addDialogDismissButtons(self.CreateButtonSizer(wx.OK | wx.CANCEL))
		self.Bind(wx.EVT_BUTTON, self.on_ok, id=wx.ID_OK)
		main_sizer.Add(main_sizer_helper.sizer, border = gui.guiHelper.BORDER_FOR_DIALOGS, flag=wx.ALL)
		main_sizer.Fit(self)
		self.SetSizer(main_sizer)
		self.Center(wx.BOTH | wx.CENTER_ON_SCREEN)
		self.Show()
		self.key.SetFocus()

	def on_ok(self, evt):
		if not self.isLicensed:
			self.activate(evt)
		else:
			self.deactivate(evt)

	def activate(self, evt):
		if not self.key.Value:
			gui.messageBox(_("You must enter a valid license key."), _("Error"), wx.OK | wx.ICON_ERROR)
			self.key.SetFocus()
			return
		progressDialog = gui.IndeterminateProgressDialog(self, _("Performing request"), _("Please wait while your license is being activated..."))

		try:
			success, message = watchdog.cancellableExecute(self.lib.ActivateLicense, self.key.Value)
		except:
			success = False
			message = _("There was an error while performing your request.")

		if not success:
			wx.CallAfter(gui.messageBox,
				_("An error has occured:\n{error}").format(error=message),
					_("Error"), wx.OK | wx.ICON_ERROR)
		else:
			evt.Skip()
			wx.CallAfter(gui.messageBox,
				_("UnicornDVC has been activated!\nAdditional info: {message}").format(message=message),
					_("Congratulations!"), wx.OK | wx.ICON_EXCLAMATION)
		progressDialog.done()

	def deactivate(self, evt):
		progressDialog = gui.IndeterminateProgressDialog(self, _("Performing request"), _("Please wait while your license is being deactivated..."))

		try:
			success, message = watchdog.cancellableExecute(self.lib.DeactivateLicense)
		except:
			success = False
			message = _("There was a timeout while performing your request.")

		if not success:
			wx.CallAfter(gui.messageBox,
				_("An error has occured:\n{error}").format(error=message),
					_("Error"), wx.OK | wx.ICON_ERROR)
		else:
			evt.Skip()
			wx.CallAfter(gui.messageBox,
				_("UnicornDVC has been deactivated!\nAdditional info: {message}").format(message=message),
					_("Congratulations!"), wx.OK | wx.ICON_EXCLAMATION)
		progressDialog.done()
