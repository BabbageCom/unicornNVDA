import sys
import os
import json
import threading
import urllib
import wx
import gui
import serializer
import transport
from .unicorn import *
from ctypes import byref, create_unicode_buffer, WinError
import watchdog
import addonHandler
addonHandler.initTranslation()
from gui.settingsDialogs import SettingsPanel

class UnicornPanel(SettingsPanel):
	title = _("UnicornDVC")

	def makeSettings(self, sizer):
		sizer_helper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		self.autoConnectSlaveCheckBox = sizer_helper.addItem(wx.CheckBox(self, wx.ID_ANY, label=_("Auto-connect in server mode on startup")))
		self.autoConnectSlaveCheckBox.Value = config.conf["unicorn"]["autoConnectSlave"]
		self.autoConnectMasterCheckBox = sizer_helper.addItem(wx.CheckBox(self, wx.ID_ANY, label=_("Auto-connect in client mode on startup")))
		self.autoConnectMasterCheckBox.Value = config.conf["unicorn"]["autoConnectMaster"]
		self.autoConnectMasterCheckBox.Enable(bool(unicorn_client()))

	def onSave(self):
		config.conf["unicorn"]["autoConnectSlave"] = self.autoConnectSlaveCheckBox.Value
		config.conf["unicorn"]["autoConnectMaster"] = self.autoConnectMasterCheckBox.Value

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
