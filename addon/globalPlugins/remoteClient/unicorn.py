import os
try:
	import winreg
except:
	import _winreg as winreg
import sys
from ctypes import *
from ctypes.wintypes import *

ARCHITECTURE=len(bin(sys.maxsize)[1:])
CTYPE_SERVER=0
CTYPE_CLIENT=1

def unicorn_lib_path():
	try:
		with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\UnicornDVC",0,winreg.KEY_READ|winreg.KEY_WOW64_32KEY) as k:
			location = os.path.join(winreg.QueryValueEx(k,"InstallLocation")[0],'lib64' if ARCHITECTURE==64 else 'lib')
	except WindowsError:
		# Assume the lib is in the current directory
		location = os.path.abspath(os.path.dirname(__file__))
	standardLibPath=os.path.join(location,'UnicornDVCAppLib.dll')
	if os.path.isfile(standardLibPath):
		return str(standardLibPath)
	return None

def vdp_rdpvcbridge_path():
	try:
		with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\UnicornDVC",0,winreg.KEY_READ|winreg.KEY_WOW64_32KEY) as k:
			location = os.path.join(winreg.QueryValueEx(k,"InstallLocation")[0],'lib64' if ARCHITECTURE==64 else 'lib')
	except WindowsError:
		# Assume the lib is in the current directory
		location = os.path.abspath(os.path.dirname(__file__))
	bridgeLibPath=os.path.join(location,'vdp_rdpvcbridge.dll')
	if os.path.isfile(bridgeLibPath):
		return bridgeLibPath
	return None

def unicorn_client():
	try:
		return bool(winreg.OpenKey(winreg.HKEY_CURRENT_USER,"SOFTWARE\\Microsoft\\Terminal Server Client\\Default\\Addins\\UnicornDVCPlugin"))
	except WindowsError:
		return False

class Unicorn(object):
	"""Class to facilitate DVC communication using the Unicorn DVC library"""

	def __init__(self, callbackHandler, supportView=True):
		if not isinstance(callbackHandler, UnicornCallbackHandler):
			raise TypeError("callbackHandler must be of type UnicornCallbackHandler")
		self.callbackHandler=callbackHandler
		self.supportView=supportView
		lib_path=unicorn_lib_path()
		if supportView:
			# Try to load the vdp_rdpvcbridge so UNicorn can find it regardless of its path
			try:
				self.vdp_bridge=windll.vdp_rdpvcbridge
			except WindowsError:
				vdp_bridge_path=vdp_rdpvcbridge_path()
				if vdp_bridge_path:
					try:
						self.vdp_bridge=WinDLL(vdp_bridge_path)
					except:
						self.vdp_bridge=None
		# Load Unicorn
		try:
			self.lib=windll.UnicornDVCAppLib
		except WindowsError:
			if not lib_path:
				raise RuntimeError("UnicornDVC library not found")
			self.lib=WinDLL(lib_path)
		self.closed = False
		self.initialized = False
		self.Initialize=None
		self.Open=None
		self.Write=None
		self.Close=None
		self.Terminate=None
		self.SetCallbacks=None
		self.registerFunctions()
		self.registerCallbacks(callbackHandler)

	def registerCallbacks(self, callbackHandler):
		callbacks=("Connected","Disconnected","Terminated","OnNewChannelConnection","OnDataReceived","OnReadError","OnClose")
		callbackPointers=(cast(getattr(callbackHandler,"c_%s"%callback),POINTER(c_void_p)) for callback in callbacks)
		self.SetCallbacks(*callbackPointers)

	def registerFunctions(self):
		self.Initialize=WINFUNCTYPE(DWORD,c_uint8)(('Unicorn_Initialize',self.lib),((1,'connectionType'),))
		self.Open=WINFUNCTYPE(DWORD)(('Unicorn_Open',self.lib))
		self.Write=WINFUNCTYPE(DWORD,DWORD,POINTER(BYTE))(('Unicorn_Write',self.lib),((1,'cbSize'),(1,'pBuffer')))
		self.Close=WINFUNCTYPE(DWORD)(('Unicorn_Close',self.lib))
		self.Terminate=WINFUNCTYPE(DWORD)(('Unicorn_Terminate',self.lib))
		self.SetCallbacks=WINFUNCTYPE(c_void_p,POINTER(c_void_p),POINTER(c_void_p),POINTER(c_void_p),POINTER(c_void_p),POINTER(c_void_p),POINTER(c_void_p),POINTER(c_void_p))(('Unicorn_SetCallbacks',self.lib),((1,'_Connected'),(1,'_Disconnected'),(1,'_Terminated'),(1,'OnNewChannelConnection'),(1,'OnDataReceived'),(1,'OnReadError'),(1,'OnClose')))

class UnicornCallbackHandler(object):

	def __init__(self):
		self.c_Connected=WINFUNCTYPE(DWORD)(self._Connected)
		self.c_Disconnected=WINFUNCTYPE(DWORD, DWORD)(self._Disconnected)
		self.c_Terminated=WINFUNCTYPE(DWORD)(self._Terminated)
		self.c_OnNewChannelConnection=WINFUNCTYPE(DWORD)(self._OnNewChannelConnection)
		self.c_OnDataReceived=WINFUNCTYPE(DWORD,DWORD,POINTER(BYTE))(self._OnDataReceived)
		self.c_OnReadError=WINFUNCTYPE(DWORD,DWORD)(self._OnReadError)
		self.c_OnClose=WINFUNCTYPE(DWORD)(self._OnClose)

	def _Connected(self):
		raise NotImplementedError

	def _Disconnected(self,dwDisconnectCode):
		raise NotImplementedError

	def _Terminated(self):
		raise NotImplementedError

	def _OnNewChannelConnection(self):
		raise NotImplementedError

	def _OnDataReceived(self,cbSize,data):
		raise NotImplementedError

	def _OnReadError(self,dwError):
		raise NotImplementedError

	def _OnClose(self):
		raise NotImplementedError
