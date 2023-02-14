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


class UnicornPanel(SettingsPanel):
	title = _("UnicornDVC")

	def makeSettings(self, settingsSizer: wx.BoxSizer) -> None:
		sizer_helper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		self.autoConnectSlaveCheckBox = sizer_helper.addItem(
			wx.CheckBox(self, wx.ID_ANY, label=_("Auto-connect in server mode on startup"))
		)
		self.autoConnectSlaveCheckBox.Value = config.conf["unicorn"]["autoConnectServer"]
		self.autoConnectMasterCheckBox = sizer_helper.addItem(
			wx.CheckBox(self, wx.ID_ANY, label=_("Auto-connect in client mode on startup"))
		)
		self.autoConnectMasterCheckBox.Value = config.conf["unicorn"]["autoConnectClient"]
		self.autoConnectMasterCheckBox.Enable(bool(unicorn.unicorn_client()))

		licenseButton = sizer_helper.addItem(wx.Button(self, label=_("Manage Unicorn license...")))
		licenseButton.Bind(wx.EVT_BUTTON,self.onLicense)

	def onLicense(self, evt) -> None:
		with UnicornLicenseDialog(self) as dlg:
			dlg.ShowModal()

	def onSave(self) -> None:
		config.conf["unicorn"]["autoConnectServer"] = self.autoConnectSlaveCheckBox.Value
		config.conf["unicorn"]["autoConnectClient"] = self.autoConnectMasterCheckBox.Value


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
