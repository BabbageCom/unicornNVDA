# Unicorn NVDA

## Table of Contents

- [About](#about)
- [Getting Started](#getting_started)
- [Usage](#usage)

## About <a name = "about"></a>

UnicornNVDA is a add-on, which facilitates communication between NVDA and the external Unicorn library. The addon handles the exchange of information between the local and remote instants of NVDA e.g., braille/speech input as well as output. The addon creates a simple manner to make use of the UnicornDVC library.

The lastest version of the addon and the library can be downloaded from the [Babbage](https://babbage.com/software-low-non-vision/) website.

## Getting Started <a name = "getting_started"></a>

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes. Unicorn NVDA is a python project that runs on a virtual environment.

### Prerequisites

To run the project a few things are requied
* SCons: software construction tool. See scons [documentation](https://scons.org/doc/production/HTML/scons-user/ch01s02.html) or [download](https://scons.org/pages/download.html) pages for more info on installing SCons
* A 32bit python version, the latest version can be found on their [downloads page](https://www.python.org/downloads/).
* NVDA, the latest version can be found on their [downloads page](https://www.nvaccess.org/download/).
* UnicornDVC, the latest version can be found on access4u's [downloads page](https://access4u.eu/downloads/).

### Installing

Installing the project is quite straightforward.
1. Clone the project locally.
2. Run the command  ```py -m SCons``` in the root folder terminal. This will build the project and output the unicornaddon.
3. (Optional) You can add a .env to the root folder to enable intellisense for libraries in NVDA. To do that you will first need to install the NvdaDevEnvironment, follow this well written [guide](https://github.com/nvaccess/nvda/blob/master/projectDocs/dev/createDevEnvironment.md). Next add a file named ```.env``` to the root folder, next add ```PYTHONPATH="PathNameToNvdaDirectory"``` to the ```.env``` file.
5. Double clicking the addon while NVDA is open will allow you to install the addon for NVDA.

## Usage <a name = "usage"></a>

### File & Code structure

The code of the project can be found in the ```addon/globalPlugins/unicorn``` folder. ```The addon/doc``` contains the localization files.

* The ```_init_.py``` contains the initialization code as well as the callback functions that are called by NVDA. It creates the DVCtransport and DialogSettings, as well as handling the callbacks called by NVDA itself.
* The ```transport.py``` contains the functionality of the callback code for the UnicornDVC. The transport class handles the transporting of the data e.g., braille or speech from Nvda Client to Nvda Server and vice versa. It does this through the Unicorn class defined in the ```unicorn.py``` and calls a variety of callbacks as well as exposing callbacks to the applib. Important callbacks called here are e.g., ```OnNewChannelConnection()```, ```Write()```, etc.
* The ```unicorn.py``` contains the callbackshandler from NVDA to the applib and vice versa. This class allows the unicorn applib to call functions. 

### How to test/debug

As the code runs on a virtual development environment, we can't quite debug with a console as one would be used to from traditional debuggers. Instead as this is an addon being ran by NVDA we need to adjust the logging level in the Registry Editor at: ```Computer\HKEY_CURRENT_USER\Software\ACCESS4U\UnicornDVC``` Setting the logging level to 5 will log up to debug level; setting the logging level to 6, the highest level, will log up to verbose level. Additionally you can enable debug mode in nvda by restarting it with debug enabled or adjusting it in the settings.

The logs can be found in the ```%Temp%``` folder on your operating machine. In the Temp folder you can find the following files:
* ```nvda.log``` This contains the output of nvda and the logs that you will output using the loghandler.
* ```UnicornDVCAppLib_DatePrintedInNumbers.log``` This contains the output of the applib from the UnicornDVC library.
* ```UnicornDVCPlugin_DatePrintedInNumbers.log``` This contains the output of the plugin from the UnicornDVC library.

The applib and plugin logs are **only** created when connecting as client/server or connecting to RDP respectively. These logs orignate from the **UnicornDVC**, for documentation as to what the errors and logs definitions visit [Access4u](https://access4u.eu/unicornnvda/).


