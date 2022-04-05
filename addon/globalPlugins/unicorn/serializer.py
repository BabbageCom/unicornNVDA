import sys
import os
import json
import speech.commands
from logHandler import log
from . import callbackCommandsDatabase

class JSONSerializer:
	SEP = '\n'

	def serialize(self, type=None, **obj):
		obj['type'] = type
		data = json.dumps(obj, cls=CustomEncoder) + self.SEP
		return data

	def deserialize(self, data):
		obj = json.loads(data, object_hook=as_sequence)
		return obj


SEQUENCE_CLASSES = (
	speech.commands.SynthCommand,
	speech.commands.EndUtteranceCommand,
	speech.commands.CallbackCommand
)


class CustomEncoder(json.JSONEncoder):

	def default(self, obj):
		if is_subclass_or_instance(obj, SEQUENCE_CLASSES):

			# special case for callback command
			if is_subclass_or_instance(obj, (speech.commands.CallbackCommand,)):
				callbackFunction = obj._callback
				callbackCommandsDatabase.ii += 1
				# save to be called function on remote session
				callbackCommandsDatabase.callBackDatabase[callbackCommandsDatabase.ii] = callbackFunction
				callbackDict = {"compName": callbackCommandsDatabase.compName, "index": callbackCommandsDatabase.ii}
				return ['callbackCommandBounce', callbackDict]

			else:
				return [obj.__class__.__name__, obj.__dict__]

		return super().default(obj)

def is_subclass_or_instance(unknown, possible):
	try:
		return issubclass(unknown, possible)
	except TypeError:
		return isinstance(unknown, possible)


def makeCallBackCommandWrapper(compName, index):
	import globalPluginHandler

	plugin = next((p for p in globalPluginHandler.runningPlugins if p.__module__ == 'globalPlugins.usa'), None)
	remoteHandler = plugin.remoteHandler if plugin else None

	def _callBackWrapper(computerName = compName, ii = index):
		return remoteHandler.transport.send(type="callbackCommandBounce", compName = computerName, index = ii)

	return speech.commands.CallbackCommand(_callBackWrapper)


def as_sequence(dct):
	if not ('type' in dct and dct['type'] == 'speak' and 'sequence' in dct):
		return dct
	sequence = []
	for item in dct['sequence']:
		if not isinstance(item, list):
			sequence.append(item)
			continue
		name, values = item

		# deserialize callback command that directly bounces back the callback to the remote server that should call it
		if name == 'callbackCommandBounce':
			inst = makeCallBackCommandWrapper(compName=values['compName'], index=values['index'])
			sequence.append(inst)
			continue

		if not hasattr(speech.commands, name):
			log.warning("Unknown sequence type received: %r" % name)
			continue
		cls = getattr(speech.commands, name)
		if not issubclass(cls, SEQUENCE_CLASSES):
			log.warning(f"Unknown sequence type received: {name!r}")
			continue
		cls = cls.__new__(cls)
		cls.__dict__.update(values)
		sequence.append(cls)
	dct['sequence'] = sequence
	return dct
