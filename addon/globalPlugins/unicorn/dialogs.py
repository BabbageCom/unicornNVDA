import wx
import gui
import gui.guiHelper
from . import unicorn
from logHandler import log
import watchdog
import addonHandler
from gui.settingsDialogs import SettingsPanel
import config
addonHandler.initTranslation()

class ConnectionStateHandler():
	def resetToDefault(self):
		self.nvdaToApplib = True
		self.applibToPlugin = True
		self.pluginToApplibServer = True
		self.wfapiAvailable = unicorn.Unicorn.check_wfapi_dll()
		self.vdpvcbridgeAvailable = unicorn.Unicorn.check_vdp_rdpvcbridge_dll()
		self.connectionType = unicorn.CTYPE.CLIENT

	def __init__(self):
		self.resetToDefault()
  
	def statusNvdaToApplibChanged(self, winError: int) -> bool:
		if (winError != 0):
			self.nvdaToApplib = False
		else:
			self.nvdaToApplib = True

	def statusApplibToPluginChanged(self, winError: int) -> bool:
		if (winError == 1722 or winError == 2250 or winError == 31 or winError == 1 or winError == 21):
			self.applibToPlugin = False
		else:	
			self.applibToPlugin = True

	def statusPluginToApplibChanged(self, winError: int) -> bool:
		if (winError == 1722):
			self.pluginToApplibServer = False
		else:
			self.pluginToApplibServer = True


Conn_State_Handler: ConnectionStateHandler = ConnectionStateHandler()

class UnicornPanel(SettingsPanel):
	title = _("UnicornDVC")
 
	def makeSettings(self, settingsSizer: wx.BoxSizer) -> None:
		sizer_helper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		self.intermediate_Horizontal_Helper = gui.guiHelper.BoxSizerHelper(self, orientation=wx.HORIZONTAL)
		self.left_Helper = gui.guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)
		self.right_Helper = gui.guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)
  
		# Left hand side: unicorn settings readwrite
		self.autoConnectSlaveCheckBox = self.left_Helper.addItem(
			wx.CheckBox(self, wx.ID_ANY, label=_("Auto-connect in server mode on startup"))
		)
		self.autoConnectSlaveCheckBox.Value = config.conf["unicorn"]["autoConnectServer"]

		self.autoConnectMasterCheckBox = self.left_Helper.addItem(
			wx.CheckBox(self, wx.ID_ANY, label=_("Auto-connect in client mode on startup"))
		)
		self.autoConnectMasterCheckBox.Value = config.conf["unicorn"]["autoConnectClient"]
		self.autoConnectMasterCheckBox.Enable(bool(unicorn.unicorn_client()))

		self.alwaysReceiveRemoteBraille = self.left_Helper.addItem(
			wx.CheckBox(self, wx.ID_ANY, label=_("always receive remote braille"))
		)
		self.alwaysReceiveRemoteBraille.Value = config.conf["unicorn"]["alwaysReceiveRemoteBraille"]
		self.alwaysReceiveRemoteBraille.Enable(bool(unicorn.unicorn_client()))

		self.cutOffLargeMesssagesCheckBox = self.left_Helper.addItem(
			wx.CheckBox(self, wx.ID_ANY, label=_("Cut-off messages above 5000 bytes"))
		)
		self.cutOffLargeMesssagesCheckBox.Value = config.conf["unicorn"]["limitMessageSize"]
		self.cutOffLargeMesssagesCheckBox.Enable(bool(unicorn.unicorn_client()))

		licenseButton = self.left_Helper.addItem(wx.Button(self, label=_("Manage Unicorn license...")))
		licenseButton.Bind(wx.EVT_BUTTON,self.onLicense)
  
		# Right hand side: nvda-unicorn connection status. The checkboxes are readonly
		global Conn_State_Handler
		self.nvdaconnectedCheckBox = self.right_Helper.addItem(
			wx.CheckBox(self, wx.ID_ANY, label=_("Nvda connected to applib"))
		)
		self.nvdaconnectedCheckBox.Value = Conn_State_Handler.nvdaToApplib
		self.nvdaconnectedCheckBox.Enable(False)
		
		self.applibConnectedCheckBox = self.right_Helper.addItem(
			wx.CheckBox(self, wx.ID_ANY, label=_("Applib connected to plugin"))
		)
		self.applibConnectedCheckBox.Value = Conn_State_Handler.applibToPlugin
		self.applibConnectedCheckBox.Enable(False)

		self.pluginConnectedCheckbox = self.right_Helper.addItem(
			wx.CheckBox(self, wx.ID_ANY, label= _("Plugin connected to server applib"))
		)
		self.pluginConnectedCheckbox.Value = Conn_State_Handler.pluginToApplibServer
		self.pluginConnectedCheckbox.Enable(False)

		self.wfapiCheckbox = self.right_Helper.addItem(
			wx.CheckBox(self, wx.ID_ANY, label= _("wfapi.dll available (citrix server only)"))
		)
		self.wfapiCheckbox.Value = Conn_State_Handler.wfapiAvailable
		self.wfapiCheckbox.Enable(False)
		self.vdpvcbridgeCheckbox = self.right_Helper.addItem(
			wx.CheckBox(self, wx.ID_ANY, label= _("vdp_rdpvcbridge.dll available (vmware server only)"))
		)
		self.vdpvcbridgeCheckbox.Value = Conn_State_Handler.vdpvcbridgeAvailable
		self.vdpvcbridgeCheckbox.Enable(False)

		self.Timer = wx.Timer(self)
		self.Bind(wx.EVT_TIMER, self.updateConnectionStatuses, self.Timer)
		self.Timer.Start(500)

		self.intermediate_Horizontal_Helper.addItem(self.left_Helper, border = (1), flag=wx.ALL)
		self.intermediate_Horizontal_Helper.addItem(self.right_Helper, border = (1), flag=wx.ALL)
		sizer_helper.addItem(self.intermediate_Horizontal_Helper, border = (1), flag=wx.ALL)
  
	def updateConnectionStatuses(self, evt):
		global Conn_State_Handler
		if Conn_State_Handler.connectionType == unicorn.CTYPE.CLIENT:
			self.pluginConnectedCheckbox.Show()
			self.wfapiCheckbox.Hide()
			self.vdpvcbridgeCheckbox.Hide()
		else:
			self.pluginConnectedCheckbox.Hide()
			self.wfapiCheckbox.Show()
			self.vdpvcbridgeCheckbox.Show()
		self.nvdaconnectedCheckBox.Value   = Conn_State_Handler.nvdaToApplib
		self.applibConnectedCheckBox.Value = Conn_State_Handler.applibToPlugin
		self.pluginConnectedCheckbox.Value = Conn_State_Handler.pluginToApplibServer
		self.wfapiCheckbox.Value = Conn_State_Handler.wfapiAvailable
		self.vdpvcbridgeCheckbox.Value = Conn_State_Handler.vdpvcbridgeAvailable

	def onLicense(self, evt) -> None:
		with UnicornLicenseDialog(self) as dlg:
			dlg.ShowModal()

	def onSave(self) -> None:
		config.conf["unicorn"]["autoConnectServer"] = self.autoConnectSlaveCheckBox.Value
		config.conf["unicorn"]["autoConnectClient"] = self.autoConnectMasterCheckBox.Value
		config.conf["unicorn"]["limitMessageSize"] = self.cutOffLargeMesssagesCheckBox.Value
		config.conf["unicorn"]["alwaysReceiveRemoteBraille"] = self.alwaysReceiveRemoteBraille.Value
		self.Timer.Stop()
	
	def onDiscard(self):
		self.Timer.Stop()

class UnicornLicenseDialog(wx.Dialog):

	def __init__(self, parent):
		if not bool(unicorn.unicorn_client()):
			wx.CallAfter(
				gui.messageBox,
				_("The UnicornDVC client is not available on your system. Managing a license is therefore not supported."),
				_("Error"),
				wx.OK | wx.ICON_ERROR
			)
			return
		# Create a temporary instance of the Unicorn object.
		try:
			self.handler = unicorn.UnicornCallbackHandler()
			self.lib = unicorn.Unicorn(unicorn.CTYPE.CLIENT, self.handler)
		except AttributeError:
			wx.CallAfter(
				gui.messageBox,
				_("The UnicornDVC client available on your system is out of date. Managing a license is therefore not supported."),
				_("Error"),
				wx.OK | wx.ICON_ERROR
			)
			raise
		super().__init__(parent, id=wx.ID_ANY, title=_("Manage Unicorn License"))
		self.isLicensed = self.lib.IsLicensed()
		if self.isLicensed:
			message = _("Your copy of UnicornDVC is properly licensed.\nChoose OK to deactivate the product, or Cancel to close this dialog.")
		else:
			message = _("Your copy of UnicornDVC doesn't seem to be licensed.\nEnter your license key in the respective field and choose OK to activate the product.\nAlternatively, press Cancel to close this dialog.")
		main_sizer = wx.BoxSizer(wx.VERTICAL)
		main_sizer.Add(wx.StaticText(self, label=message))
		main_sizer_helper = gui.guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)
		# Translators: The input field to enter the Unicorn license key
		self.key = main_sizer_helper.addLabeledControl(_("&License Key:"), wx.TextCtrl)
		self.key.Enabled = not self.isLicensed
		main_sizer_helper.addDialogDismissButtons(self.CreateButtonSizer(wx.OK | wx.CANCEL))
		self.Bind(wx.EVT_BUTTON, self.on_ok, id=wx.ID_OK)
		main_sizer.Add(main_sizer_helper.sizer, border=gui.guiHelper.BORDER_FOR_DIALOGS, flag=wx.ALL)
		main_sizer.Fit(self)
		self.SetSizer(main_sizer)
		self.Center(wx.BOTH )
		self.Show()
		self.key.SetFocus()

	def on_ok(self, evt) -> None:
		if not self.isLicensed:
			self.activate(evt)
		else:
			self.deactivate(evt)

	def activate(self, evt) -> None:
		if not self.key.Value:
			gui.messageBox(_("You must enter a valid license key."), _("Error"), wx.OK | wx.ICON_ERROR)
			self.key.SetFocus()
			return
		progressDialog = gui.IndeterminateProgressDialog(self, _("Performing request"), _("Please wait while your license is being activated..."))

		try:
			success, message = watchdog.cancellableExecute(self.lib.ActivateLicense, self.key.Value)
		except Exception:
			success = False
			message = _("There was an error while performing your request.")
			log.error("Activation error", exc_info=True)

		if not success:
			wx.CallAfter(
				gui.messageBox,
				_("An error has occured:\n{error}").format(error=message),
				_("Error"),
				wx.OK | wx.ICON_ERROR
			)
		else:
			evt.Skip()
			wx.CallAfter(
				gui.messageBox,
				_("UnicornDVC has been activated!\nAdditional info: {message}").format(message=message),
				_("Congratulations!"), wx.OK | wx.ICON_EXCLAMATION
			)
		progressDialog.done()

	def deactivate(self, evt) -> None:
		progressDialog = gui.IndeterminateProgressDialog(self, _("Performing request"), _("Please wait while your license is being deactivated..."))

		try:
			success, message = watchdog.cancellableExecute(self.lib.DeactivateLicense)
		except:
			success = False
			message = _("There was a timeout while performing your request.")
			log.error("Activation error", exc_info=True)

		if not success:
			wx.CallAfter(
				gui.messageBox,
				_("An error has occured:\n{error}").format(error=message),
				_("Error"),
				wx.OK | wx.ICON_ERROR
			)
		else:
			evt.Skip()
			wx.CallAfter(
				gui.messageBox,
				_("UnicornDVC has been deactivated!\nAdditional info: {message}").format(message=message),
				_("Congratulations!"),
				wx.OK | wx.ICON_EXCLAMATION
			)
		progressDialog.done()
