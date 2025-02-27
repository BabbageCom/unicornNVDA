import ctypes

import addonHandler
import config
import core
import gui
import gui.guiHelper
import queueHandler
import watchdog
import wx
from gui.settingsDialogs import SettingsPanel
from logHandler import log

from . import unicorn

addonHandler.initTranslation()


class ConnectionStateHandler:
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
        if winError != 0:
            self.nvdaToApplib = False
        else:
            self.nvdaToApplib = True

    def statusApplibToPluginChanged(self, winError: int) -> bool:
        if (
            winError == 1722
            or winError == 2250
            or winError == 31
            or winError == 1
            or winError == 21
        ):
            self.applibToPlugin = False
        else:
            self.applibToPlugin = True

    def statusPluginToApplibChanged(self, winError: int) -> bool:
        if winError == 1722:
            self.pluginToApplibServer = False
        else:
            self.pluginToApplibServer = True


Conn_State_Handler: ConnectionStateHandler = ConnectionStateHandler()


class UnicornPanel(SettingsPanel):
    title = _("UnicornDVC")

    def makeSettings(self, settingsSizer: wx.BoxSizer) -> None:
        sizer_helper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
        self.intermediate_Horizontal_Helper = gui.guiHelper.BoxSizerHelper(
            self, orientation=wx.HORIZONTAL
        )
        self.left_Helper = gui.guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)
        self.right_Helper = gui.guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)

        # Left hand side: unicorn settings readwrite

        self.autoConnectNoneRadioButton = self.left_Helper.addItem(
            wx.RadioButton(
                self,
                wx.ID_ANY,
                label=_("No auto-connect on start-up"),
                style=wx.RB_GROUP,
            )
        )
        self.autoConnectNoneRadioButton.Value = (
            not config.conf["unicorn"]["autoConnectServer"]
            and not config.conf["unicorn"]["autoConnectClient"]
        )

        self.autoConnectRemoteRadioButton = self.left_Helper.addItem(
            wx.RadioButton(
                self,
                wx.ID_ANY,
                label=_("Auto-connect to local workstation on start-up"),
            )
        )
        self.autoConnectRemoteRadioButton.Value = config.conf["unicorn"][
            "autoConnectServer"
        ]

        self.autoConnectLocalRadioButton = self.left_Helper.addItem(
            wx.RadioButton(
                self,
                wx.ID_ANY,
                label=_("Auto-connect to remote workstation on start-up"),
            )
        )
        self.autoConnectLocalRadioButton.Value = config.conf["unicorn"][
            "autoConnectClient"
        ]

        self.cutOffLargeMesssagesCheckBox = self.left_Helper.addItem(
            wx.CheckBox(self, wx.ID_ANY, label=_("Cut-off messages above 5000 bytes"))
        )
        self.cutOffLargeMesssagesCheckBox.Value = config.conf["unicorn"][
            "limitMessageSize"
        ]
        self.cutOffLargeMesssagesCheckBox.Enable(bool(unicorn.unicorn_client()))

        licenseButton = self.left_Helper.addItem(
            wx.Button(self, label=_("Manage Unicorn license..."))
        )
        licenseButton.Bind(wx.EVT_BUTTON, self.onLicense)

        # Right hand side: nvda-unicorn connection status. The checkboxes are readonly
        global Conn_State_Handler
        self.nvdaconnectedCheckBox = self.right_Helper.addItem(
            wx.CheckBox(self, wx.ID_ANY, label=_("NVDA connected to AppLib"))
        )
        self.nvdaconnectedCheckBox.Value = Conn_State_Handler.nvdaToApplib
        self.nvdaconnectedCheckBox.Enable(False)

        self.applibConnectedCheckBox = self.right_Helper.addItem(
            wx.CheckBox(self, wx.ID_ANY, label=_("AppLib connected to plugin"))
        )
        self.applibConnectedCheckBox.Value = Conn_State_Handler.applibToPlugin
        self.applibConnectedCheckBox.Enable(False)

        self.pluginConnectedCheckbox = self.right_Helper.addItem(
            wx.CheckBox(self, wx.ID_ANY, label=_("Plugin connected to remote AppLib"))
        )
        self.pluginConnectedCheckbox.Value = Conn_State_Handler.pluginToApplibServer
        self.pluginConnectedCheckbox.Enable(False)

        self.wfapiCheckbox = self.right_Helper.addItem(
            wx.CheckBox(
                self, wx.ID_ANY, label=_("wfapi.dll available (Citrix remote only)")
            )
        )
        self.wfapiCheckbox.Value = Conn_State_Handler.wfapiAvailable
        self.wfapiCheckbox.Enable(False)
        self.vdpvcbridgeCheckbox = self.right_Helper.addItem(
            wx.CheckBox(
                self,
                wx.ID_ANY,
                label=_("vdp_rdpvcbridge.dll available (VMware remote only)"),
            )
        )
        self.vdpvcbridgeCheckbox.Value = Conn_State_Handler.vdpvcbridgeAvailable
        self.vdpvcbridgeCheckbox.Enable(False)

        self.Timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.updateConnectionStatuses, self.Timer)
        self.Timer.Start(500)

        self.intermediate_Horizontal_Helper.addItem(
            self.left_Helper, border=(1), flag=wx.ALL
        )
        self.intermediate_Horizontal_Helper.addItem(
            self.right_Helper, border=(1), flag=wx.ALL
        )
        sizer_helper.addItem(
            self.intermediate_Horizontal_Helper, border=(1), flag=wx.ALL
        )

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
        self.nvdaconnectedCheckBox.Value = Conn_State_Handler.nvdaToApplib
        self.applibConnectedCheckBox.Value = Conn_State_Handler.applibToPlugin
        self.pluginConnectedCheckbox.Value = Conn_State_Handler.pluginToApplibServer
        self.wfapiCheckbox.Value = Conn_State_Handler.wfapiAvailable
        self.vdpvcbridgeCheckbox.Value = Conn_State_Handler.vdpvcbridgeAvailable

    def onLicense(self, evt) -> None:
        with UnicornLicenseDialog(self) as dlg:
            dlg.ShowModal()

    def onSave(self) -> None:
        config.conf["unicorn"][
            "autoConnectServer"
        ] = self.autoConnectRemoteRadioButton.Value
        config.conf["unicorn"][
            "autoConnectClient"
        ] = self.autoConnectLocalRadioButton.Value
        config.conf["unicorn"][
            "limitMessageSize"
        ] = self.cutOffLargeMesssagesCheckBox.Value
        config.conf["unicorn"]["alwaysReceiveRemoteBraille"] = False
        self.Timer.Stop()

    def onDiscard(self):
        self.Timer.Stop()


a4uLicenseMessageMapping = {
    "to verify there are activations remaining, and the API Key and Product ID are correct.": _("This license key is not valid for this product."),  # type: ignore
    "customer account does not exist for this API Key.": _("This license key is not valid."),  # type: ignore
    "not activate API Key. No API resources available.": _("No activations remaining."),  # type: ignore
}


# something can go wrong with the conversion in the dll when tranlating the json return to some string class in c++,
# this causes that in the beginning of the error message some chinese characters appear, thus we check if the message
# ends with a known message and return the correct message
def getMessageEndWithA4uLicenseMessage(message):
    for key in a4uLicenseMessageMapping:
        if message.endswith(key):
            return a4uLicenseMessageMapping[key]
    return None


class UnicornLicenseDialog(wx.Dialog):

    def __init__(self, parent):
        if not bool(unicorn.unicorn_client()):
            wx.CallAfter(
                gui.messageBox,
                _(
                    "The UnicornDVC client is not available on your system. Managing a license is therefore not supported."
                ),
                _("Error"),
                wx.OK | wx.ICON_ERROR,
            )
            return
        # Create a temporary instance of the Unicorn object.
        try:
            self.handler = unicorn.UnicornCallbackHandler()
            self.lib = unicorn.Unicorn(unicorn.CTYPE.CLIENT, self.handler)
            res = self.lib.Initialize()
            # If a different error than ERROR_ALREADY_INITIALIZED is returned
            if res and res != 1247:
                raise ctypes.WinError(res)
        except AttributeError:
            wx.CallAfter(
                gui.messageBox,
                _(
                    "The UnicornDVC client available on your system is out of date. Managing a license is therefore not supported."
                ),
                _("Error"),
                wx.OK | wx.ICON_ERROR,
            )
            raise
        super().__init__(parent, id=wx.ID_ANY, title=_("Manage Unicorn License"))
        self.isLicensed = self.lib.IsLicensed()
        if self.isLicensed:
            message = _("Your copy of UnicornDVC is properly licensed.")
        else:
            message = _("Your copy of UnicornDVC doesn't seem to be licensed.")

        top_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.buttontop_sizer_helper = gui.guiHelper.BoxSizerHelper(
            self, orientation=wx.HORIZONTAL
        )

        # Add Babbage icon
        addon: addonHandler.Addon = addonHandler.getCodeAddon()
        path = addon.path + "\\BabbageIcon.png"
        image = wx.Image(path, wx.BITMAP_TYPE_PNG)
        image = image.Scale(115, 115, wx.IMAGE_QUALITY_HIGH)
        image_ctrl = wx.StaticBitmap(self, wx.ID_ANY, (wx.Bitmap(image)), pos=(0, 0))

        top_sizer.Add(image_ctrl, 0, wx.LEFT, 15)
        message = "Babbage\ninfo@babbage.com\n0165 536 156\n\n" + message
        top_sizer.Add(
            wx.StaticText(self, label=message),
            wx.SizerFlags(0).Align(wx.LEFT).Border(wx.LEFT, 30),
        )

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(top_sizer, 0, wx.RIGHT, 10)

        main_sizer_helper = gui.guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)

        main_sizer_helper.addItem(self.buttontop_sizer_helper, border=(1), flag=wx.ALL)
        main_sizer.Add(
            main_sizer_helper.sizer,
            border=gui.guiHelper.BORDER_FOR_DIALOGS,
            flag=wx.ALL,
        )

        self.addLicenseKeyOrDeactivateButton()

        closeButton = self.buttontop_sizer_helper.addItem(
            wx.Button(self, label=_("&Close")), flag=wx.EXPAND
        )
        closeButton.Bind(wx.EVT_BUTTON, self.onClose)
        closeButton.SetFocus()

        main_sizer.Fit(self)
        self.SetSizer(main_sizer)
        self.Center(wx.BOTH)

    def onClose(self, evt):
        self.Close()

    def addLicenseKeyOrDeactivateButton(self):
        # Translators: The input field to enter the Unicorn license key
        if not self.isLicensed:
            activationButton = self.buttontop_sizer_helper.addItem(
                wx.Button(self, label=_("activate with key")), flag=wx.EXPAND
            )
            activationButton.Bind(wx.EVT_BUTTON, self.activate)
        else:
            deActivationButton = self.buttontop_sizer_helper.addItem(
                wx.Button(self, label=_("deactivate key")), flag=wx.EXPAND
            )
            deActivationButton.Bind(wx.EVT_BUTTON, self.deactivate)

    def restartNVDA(self):
        queueHandler.queueFunction(queueHandler.eventQueue, core.restart)

    def activate(self, evt):
        success = False
        with activationDialog(self, self.lib) as dlg:
            dlg.ShowModal()
            success = dlg.success
        if success:
            self.Close()
            self.Destroy()
            wx.CallAfter(self.restartNVDA)

    def deactivate_license(self):
        (success, message) = self.lib.DeactivateLicense()
        return (success, message)

    def deactivate(self, evt):
        try:
            success, message = watchdog.cancellableExecute(self.deactivate_license)
        except Exception as e:
            success = False
            message = _(f"There was a timeout while performing your request. {e}")
            log.error("Activation error", exc_info=True)
        if not success:
            if getMessageEndWithA4uLicenseMessage(message):
                message = getMessageEndWithA4uLicenseMessage(message)
            gui.messageBox(
                _("An error has occured:\n{error}").format(error=message),
                _("Error"),
                wx.OK | wx.ICON_ERROR,
            )
        else:
            gui.messageBox(
                _(
                    "Unicorn has been deactivated! NVDA will be restarted. \nAdditional info: {message}"
                ).format(message=message),
                _("Congratulations!"),
                wx.OK | wx.ICON_EXCLAMATION,
            )
        if success:
            self.Close()
            self.Destroy()
            wx.CallAfter(self.restartNVDA)


class activationDialog(wx.Dialog):

    def __init__(self, parent, lib):
        windowStyle = wx.DEFAULT_DIALOG_STYLE | wx.STAY_ON_TOP | wx.CENTER
        super().__init__(
            parent, id=wx.ID_ANY, title=_("Manage Unicorn License"), style=windowStyle
        )

        self.lib = lib

        self.main_sizer = wx.BoxSizer(wx.VERTICAL)
        self.main_sizer_helper = gui.guiHelper.BoxSizerHelper(
            self, orientation=wx.VERTICAL
        )

        self.key = self.main_sizer_helper.addLabeledControl(
            _("&License Key:"), wx.TextCtrl
        )

        self.Bind(wx.EVT_BUTTON, self.on_ok, id=wx.ID_OK)
        self.main_sizer.Add(
            self.main_sizer_helper.sizer,
            border=gui.guiHelper.BORDER_FOR_DIALOGS,
            flag=wx.ALL,
        )
        self.main_sizer_helper.addDialogDismissButtons(
            self.CreateButtonSizer(wx.OK | wx.CANCEL)
        )
        self.main_sizer.Fit(self)
        self.SetSizer(self.main_sizer)
        self.Center(wx.BOTH)
        self.key.SetFocus()

    def on_ok(self, evt):
        self.activate()

    def activate_license(self, licenseKey):
        (success, message) = self.lib.ActivateLicense(licenseKey)
        return (success, message)

    def activate(self):
        if not self.key.Value:
            gui.messageBox(
                _("You must enter a valid license key."),
                _("Error"),
                wx.OK | wx.ICON_ERROR,
            )
            self.key.SetFocus()
            return

        try:
            self.success, message = watchdog.cancellableExecute(
                self.activate_license, self.key.Value
            )
        except Exception as e:
            self.success = False
            message = _("There was an error while performing your request. \n") + str(e)
            log.error(_("Activation error"), exc_info=True)

        if not self.success:
            if getMessageEndWithA4uLicenseMessage(message):
                message = getMessageEndWithA4uLicenseMessage(message)
            gui.messageBox(
                _("An error has occured:\n{error}").format(error=message),
                _("Error"),
                wx.OK | wx.ICON_ERROR,
            )
        else:
            gui.messageBox(
                _(
                    "Unicorn has been activated! NVDA will be restarted. \nAdditional info: {message}"
                ).format(message=message),
                _("Congratulations!"),
                wx.OK | wx.ICON_EXCLAMATION,
            )
            queueHandler.queueFunction(queueHandler.eventQueue, core.restart)
        if self.success:
            self.Close()
