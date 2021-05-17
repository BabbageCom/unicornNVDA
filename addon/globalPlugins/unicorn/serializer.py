import sys
import os
import json
import speech.commands
from logHandler import log

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
)

class CustomEncoder(json.JSONEncoder):

	def default(self, obj):
		if is_subclass_or_instance(obj, SEQUENCE_CLASSES):
			log.warning("SEQUENCE_CLASS found to serialize")
			log.warning("Name: %r" % obj.__class__.__name__)
			log.warning("Dict: %r" % obj.__class__.__dict__)
			if (obj.__class__.__name__ == "CallbackCommand"):
				log.warning("Callbackcommand found!")
			return [obj.__class__.__name__, obj.__dict__]
		log.warning("*** %r" % obj)	
		return super().default(obj)

def is_subclass_or_instance(unknown, possible):
	try:
		return issubclass(unknown, possible)
	except TypeError:
		return isinstance(unknown, possible)

def as_sequence(dct):
	if not ('type' in dct and dct['type'] == 'speak' and 'sequence' in dct):
		return dct
	sequence = []
	for item in dct['sequence']:
		if not isinstance(item, list):
			sequence.append(item)
			continue
		name, values = item
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
