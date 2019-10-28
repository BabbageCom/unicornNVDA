import wx
from . import input
import speech
import braille
import inputCore


class LocalMachine:

	def __init__(self):
		self.is_muted = False
		self.receiving_braille = False

	def cancel_speech(self, **kwargs):
		if self.is_muted:
			return
		wx.CallAfter(speech._manager.cancel)

	def speak(self, sequence, priority, **kwargs):
		if self.is_muted:
			return
		speech.beenCanceled = False
		wx.CallAfter(speech._manager.speak, sequence, priority)

	def display(self, cells, **kwargs):
		if self.receiving_braille and braille.handler.displaySize > 0 and len(cells) <= braille.handler.displaySize:
			# We use braille.handler._writeCells since this respects thread safe displays and automatically falls back to noBraille if desired
			cells = cells + [0] * (braille.handler.displaySize - len(cells))
			wx.CallAfter(braille.handler._writeCells, cells)

	def braille_input(self, **kwargs):
		try:
			inputCore.manager.executeGesture(input.BrailleInputGesture(**kwargs))
		except inputCore.NoInputGestureAction:
			pass

	def set_braille_display_size(self, sizes, **kwargs):
		sizes.append(braille.handler.display.numCells)
		try:
			size = min(i for i in sizes if i > 0)
		except ValueError:
			size = braille.handler.display.numCells
		braille.handler.displaySize = size
		braille.handler.enabled = bool(size)
