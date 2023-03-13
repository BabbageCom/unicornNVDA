import braille
import brailleInput
import api
import baseObject
import vision
import scriptHandler
import globalPluginHandler

class BrailleInputGesture(braille.BrailleDisplayGesture, brailleInput.BrailleInputGesture):

	def __init__(self, **kwargs):
		super().__init__()
		for key, value in kwargs.items():
			setattr(self, key, value)
		self.source = "remote{}{}".format(self.source[0].upper(),self.source[1:])
		self.scriptPath = getattr(self,"scriptPath",None)
		self.script = self.findScript() if self.scriptPath else None

	def findScript(self):
		if not (isinstance(self.scriptPath,list) and len(self.scriptPath)==3):
			return None
		module,cls,scriptName=self.scriptPath
		focus = api.getFocusObject()
		if not focus:
			return None
		if scriptName.startswith("kb:"):
			# Emulate a key press.
			return scriptHandler._makeKbEmulateScript(scriptName)

		import globalCommands

		# Global plugin level.
		if cls=='GlobalPlugin':
			for plugin in globalPluginHandler.runningPlugins:
				if module==plugin.__module__:
					func = getattr(plugin, "script_%s" % scriptName, None)
					if func:
						return func

		# App module level.
		app = focus.appModule
		if app and cls=='AppModule' and module==app.__module__:
			func = getattr(app, "script_%s" % scriptName, None)
			if func:
				return func

		# Vision enhancement provider level
		for provider in vision.handler.getActiveProviderInstances():
			if isinstance(provider, baseObject.ScriptableObject):
				if cls=='VisionEnhancementProvider' and module==provider.__module__:
					func = getattr(app, "script_%s" % scriptName, None)
					if func:
						return func

		# Tree interceptor level.
		treeInterceptor = focus.treeInterceptor
		if treeInterceptor and treeInterceptor.isReady:
			func = getattr(treeInterceptor , "script_%s" % scriptName, None)
			if func:
				return func

		# NVDAObject level.
		func = getattr(focus, "script_%s" % scriptName, None)
		if func:
			return func
		for obj in reversed(api.getFocusAncestors()):
			func = getattr(obj, "script_%s" % scriptName, None)
			if func and getattr(func, 'canPropagate', False):
				return func

		# Global commands.
		func = getattr(globalCommands.commands, "script_%s" % scriptName, None)
		if func:
			return func

		return None
