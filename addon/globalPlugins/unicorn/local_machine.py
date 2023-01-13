import os
import wx
from . import input
import speech
import braille
import inputCore
import nvwave
import tones
import versionInfo

def setSpeechCancelledToFalse():
	"""
	This function updates the state of speech so that it is aware that future
	speech should not be cancelled. In the long term this is a fragile solution
	as NVDA does not support modifying the internal state of speech.
	"""
	if versionInfo.version_year >= 2021:
		# workaround as beenCanceled is readonly as of NVDA#12395
		speech.speech._speechState.beenCanceled = False
	else:
		speech.beenCanceled = False


class LocalMachine:

	def __init__(self):
		self.is_muted = False
		self.receiving_braille = False
		self._cached_sizes = None

	def play_wave(self, fileName, asynchronous=True, **kwargs):
		if self.is_muted:
			return
		# Python 2 compatibility
		asynchronous = kwargs.get("async", asynchronous)
		if os.path.exists(fileName):
			nvwave.playWaveFile(fileName=fileName, asynchronous=asynchronous)

	def beep(self, hz, length, left, right, **kwargs):
		if self.is_muted:
			return
		tones.beep(hz, length, left, right)

	def cancel_speech(self, **kwargs):
		if self.is_muted:
			return
		wx.CallAfter(speech._manager.cancel)

	def speak(self, sequence, priority=speech.priorities.Spri.NORMAL, **kwargs):
		if self.is_muted:
			return
		setSpeechCancelledToFalse()
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
		if versionInfo.version_year >= 2023:
			self._cached_sizes = sizes
			return
		sizes.append(braille.handler.display.numCells)
		try:
			size = min(i for i in sizes if i > 0)
		except ValueError:
			size = braille.handler.display.numCells
		braille.handler.displaySize = size
		braille.handler.enabled = bool(size)

	def handle_filter_displaySize(self, value):
		if not self._cached_sizes:
			return value
		sizes = self._cached_sizes + [value]
		try:
			return min(i for i in sizes if i>0)
		except ValueError:
			return value

	def handle_decide_enabled(self):
		return not self.receiving_braille
