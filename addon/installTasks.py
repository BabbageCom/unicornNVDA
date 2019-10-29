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
		_("You have installed an old version of NVDA Remote, which is incompatible with the UnicornDVC add-on. Do you want to uninstall it? If you need the functionality found in NVDA Remote, you are advised to get it from the NVDA add-ons website."),
		# Translators: the title of a message box dialog.
		_("Uninstall incompatible add-on"),
		wx.YES|wx.NO|wx.ICON_WARNING) == wx.YES:
			addon.requestRemove()
