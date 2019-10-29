# -*- coding: UTF-8 -*-

import addonHandler
import gui
import wx

addonHandler.initTranslation()

def onInstall():
	for addon in addonHandler.getAvailableAddons():
		if addon.manifest['name'] == "remote" and addon.manifest['version'].endswith("+"):
			askToRemove(addon)
			break

def askToRemove(addon):
	if gui.messageBox(
		# Translators: the label of a message box dialog.
		_("You have installed an old and incompatible version of NVDA Remote. Do you want to uninstall it?"),
		# Translators: the title of a message box dialog.
		_("Uninstall incompatible add-on"),
		wx.YES|wx.NO|wx.ICON_WARNING) == wx.YES:
			addon.requestRemove()
