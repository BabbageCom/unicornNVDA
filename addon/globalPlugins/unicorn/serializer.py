import sys
import os
import json
import speech.commands
from logHandler import log
from . import callbackCommandsDatabase
from . import transport
from typing import Dict
class JSONSerializer:
	SEP = '\n'

	def serialize(self, type=None, **obj) -> str:
		obj['type'] = type
		data = json.dumps(obj, cls=CustomEncoder) + self.SEP
		return data

	def deserialize(self, data: str):
		# complicated lambda because of the callbackCommandbounce. It needs the transporter itself to send back the command
		def as_sequenceWithTransporter(dct):
			return as_sequence(dct)
		obj = json.loads(data, object_hook=as_sequenceWithTransporter)
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




class callBackCommandBounce:

	def __init__(self, compName: str, index: int):
		self.compName = compName
		self.index = index


def as_sequence(dct: Dict) -> Dict:
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
			inst = callBackCommandBounce(values['compName'], values['index'])
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
