# Third-party components and license texts

English | [简体中文](THIRD_PARTY_NOTICES_ZH.md)

The archived standalone WorldApartTrainer build contains the runtime components
below. This notice identifies their sources and the accompanying license texts;
the original license texts govern the respective components. The public source
snapshot's missing-input and build boundaries are documented in [BUILD.md](BUILD.md).

| Component | Historical build version | Source | Included texts |
| --- | --- | --- | --- |
| Python | 3.14.7, Windows x64 | [Python](https://www.python.org/) | [Python-LICENSE.txt](licenses/Python-LICENSE.txt) |
| Frida Python bindings | 17.7.3 | [Frida](https://frida.re/), [frida-python](https://github.com/frida/frida-python) | [Frida-COPYING.txt](licenses/Frida-COPYING.txt), [Frida-COPYING.LIB.txt](licenses/Frida-COPYING.LIB.txt) |
| PyInstaller bootloader and runtime hooks | 6.22.3 | [PyInstaller](https://pyinstaller.org/), [source](https://github.com/pyinstaller/pyinstaller) | [PyInstaller-COPYING.txt](licenses/PyInstaller-COPYING.txt), [runtime hook copyright notices](licenses/PyInstaller-Runtime-Notices.txt) |

The Python, Frida and PyInstaller license files were copied byte for byte from the
official distributions used for the archived build. Python's license file also
contains terms for components shipped with that Windows runtime, including bzip2,
libffi, Zstandard, Apache License 2.0, Tcl and Tk. The original `license.terms`
resources in the Tcl/Tk DLLs were retained in the standalone executable.

Frida's `COPYING` uses the wxWindows Library Licence 3.1 and refers to the GNU
Library General Public License. The additional `Frida-COPYING.LIB.txt` is the
[GNU-hosted complete GNU Library General Public License v2.0](https://www.gnu.org/licenses/old-licenses/lgpl-2.0.txt),
dated June 1991. The exception text in the original `COPYING` is retained.

PyInstaller's `COPYING.txt` contains its bootloader exception and the license
statements for its different components. The Apache-2.0 copyright headers of the
runtime hooks used by the standalone build are included in the separate runtime
notices file.

The original upstream license texts were not rewritten during packaging. The
listed Python, Frida and PyInstaller distribution component sources were not
modified for that build. Required upstream copyright and license attributions are
retained in this source export.
