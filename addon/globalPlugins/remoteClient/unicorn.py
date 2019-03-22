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
		return bool(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,r"CLSID\{E8BACC05-64F6-4534-9764-FB6698CA3362}",0,winreg.KEY_READ|winreg.KEY_WOW64_32KEY))
	except WindowsError:
		return False

class Unicorn(object):
	"""Class to facilitate DVC communication using the Unicorn DVC library"""

	def __init__(self, connectionType, callbackHandler, supportView=True, libPath=None):
		if not connectionType in (CTYPE_SERVER, CTYPE_CLIENT):
			raise ValueError("Invalid connection type")
		if not isinstance(callbackHandler, UnicornCallbackHandler):
			raise TypeError("callbackHandler must be of type UnicornCallbackHandler")
		if libPath and not os.path.isfile(libPath):
			raise ValueError("The supplied library path does not exist")
		self.lib=None
		self.connectionType=connectionType
		self.callbackHandler=callbackHandler
		self.supportView=supportView
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
		if not libPath:
			libPath=unicorn_lib_path()
			# Load Unicorn
			try:
				self.lib=windll.UnicornDVCAppLib
			except WindowsError:
				if not libPath:
					raise RuntimeError("UnicornDVC library not found")
		if libPath and not self.lib:
			self.lib=WinDLL(libPath)
		self.closed = False
		self.initialized = False
		self.registerFunctions()
		self.registerCallbacks(callbackHandler)

	def registerCallbacks(self, callbackHandler):
		callbacks=(
			"Connected",
			"Disconnected",
			"Terminated",
			"OnNewChannelConnection",
			"OnDataReceived",
			"OnReadError",
			"OnClose",
			"OnTrial",
			"OnTrialExpired",
		)
		callbackPointers=(cast(getattr(callbackHandler,"c_%s"%callback),POINTER(c_void_p)) for callback in callbacks)
		self.SetCallbacks(*callbackPointers)

	def registerFunctions(self):
		self.c_Initialize=WINFUNCTYPE(DWORD,c_uint)(('Unicorn_Initialize',self.lib),((1,'connectionType'),))
		self.c_ActivateLicense=WINFUNCTYPE(c_wchar_p, c_wchar_p, c_wchar_p, POINTER(BOOL))(('Unicorn_ActivateLicense',self.lib),((1,'emailAddress'),(1,'licenseKey'),(1,'success')))
		self.c_DeactivateLicense=WINFUNCTYPE(c_wchar_p, POINTER(BOOL))(('Unicorn_DeactivateLicense',self.lib),((1,'success'),))
		self.IsLicensed=WINFUNCTYPE(BOOL)(('Unicorn_IsLicensed',self.lib))
		self.c_Open=WINFUNCTYPE(DWORD,c_uint)(('Unicorn_Open',self.lib),((1,'connectionType'),))
		self.c_Write=WINFUNCTYPE(DWORD,c_uint,DWORD,POINTER(BYTE))(('Unicorn_Write',self.lib),((1,'connectionType'),(1,'cbSize'),(1,'pBuffer')))
		self.c_Close=WINFUNCTYPE(DWORD,c_uint)(('Unicorn_Close',self.lib),((1,'connectionType'),))
		self.c_Terminate=WINFUNCTYPE(DWORD,c_uint)(('Unicorn_Terminate',self.lib),((1,'connectionType'),))
		self.c_SetCallbacks=WINFUNCTYPE(
			c_void_p,
			c_uint,
			POINTER(c_void_p),
			POINTER(c_void_p),
			POINTER(c_void_p),
			POINTER(c_void_p),
			POINTER(c_void_p),
			POINTER(c_void_p),
			POINTER(c_void_p),
			POINTER(c_void_p),
			POINTER(c_void_p)
		)(('Unicorn_SetCallbacks',self.lib),(
			(1,'connectionType'),
			(1,'_Connected'),
			(1,'_Disconnected'),
			(1,'_Terminated'),
			(1,'_OnNewChannelConnection'),
			(1,'_OnDataReceived'),
			(1,'_OnReadError'),
			(1,'_OnClose'),
			(1,'_OnTrial'),
			(1,'_OnTrialExpired')
		))

	def Initialize(self):
		return self.c_Initialize(self.connectionType)

	def ActivateLicense(self, emailAddress, licenseKey):
		success = BOOL()
		message = self.c_ActivateLicense(emailAddress, licenseKey, byref(success))
		return (success, message)

	def DeactivateLicense(self):
		success = BOOL()
		message = self.c_DeactivateLicense(byref(success))
		return (success, message)

	def Open(self):
		return self.c_Open(self.connectionType)

	def Write(self, cbSize, pBuffer):
		return self.c_Write(self.connectionType, cbSize, pBuffer)

	def Close(self):
		return self.c_Close(self.connectionType)

	def Terminate(self):
		return self.c_Terminate(self.connectionType)

	def SetCallbacks(
		self,
		_Connected,
		_Disconnected,
		_Terminated,
		_OnNewChannelConnection,
		_OnDataReceived,
		_OnReadError,
		_OnClose,
		_OnTrial,
		_OnTrialExpired
	):
		return self.c_SetCallbacks(
			self.connectionType,
			_Connected,
			_Disconnected,
			_Terminated,
			_OnNewChannelConnection,
			_OnDataReceived,
			_OnReadError,
			_OnClose,
			_OnTrial,
			_OnTrialExpired
		)

class UnicornCallbackHandler(object):

	def __init__(self):
		self.c_Connected=WINFUNCTYPE(DWORD)(self._Connected)
		self.c_Disconnected=WINFUNCTYPE(DWORD, DWORD)(self._Disconnected)
		self.c_Terminated=WINFUNCTYPE(DWORD)(self._Terminated)
		self.c_OnNewChannelConnection=WINFUNCTYPE(DWORD)(self._OnNewChannelConnection)
		self.c_OnDataReceived=WINFUNCTYPE(DWORD,DWORD,POINTER(BYTE))(self._OnDataReceived)
		self.c_OnReadError=WINFUNCTYPE(DWORD,DWORD)(self._OnReadError)
		self.c_OnClose=WINFUNCTYPE(DWORD)(self._OnClose)
		self.c_OnTrial=WINFUNCTYPE(None)(self._OnTrial)
		self.c_OnTrialExpired=WINFUNCTYPE(None)(self._OnTrialExpired)

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

	def _OnTrial(self):
		raise NotImplementedError

	def _OnTrialExpired(self):
		raise NotImplementedError	
