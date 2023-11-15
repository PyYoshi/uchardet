# uchardet

[uchardet](https://www.freedesktop.org/wiki/Software/uchardet/) is an encoding and language detector library, which takes a sequence of bytes in an unknown character encoding without any additional information, and attempts to determine the encoding of the text.

* Returned encoding names are [iconv](https://www.gnu.org/software/libiconv/)-compatible.
* Returned language codes are ISO 639-1.

uchardet started as a C language binding of the original C++ implementation of the universal charset detection library by Mozilla. Since this far-away time, it can now detect more charsets, and much more reliably than the original implementation. Moreover it also work as a very good language detector, while still staying reasonably fast.

## Supported Languages/Encodings

  * International (Unicode)
    * UTF-8
    * UTF-16BE / UTF-16LE
    * UTF-32BE / UTF-32LE / X-ISO-10646-UCS-4-34121 / X-ISO-10646-UCS-4-21431
  * Arabic
    * UTF-8
    * ISO-8859-6
    * WINDOWS-1256
  * Belarusian
    * UTF-8
    * ISO-8859-5
    * WINDOWS-1251
  * Bulgarian
    * UTF-8
    * ISO-8859-5
    * WINDOWS-1251
  * Catalan
    * UTF-8
    * ISO-8859-1
    * WINDOWS-1252
  * Chinese
    * UTF-8
    * ISO-2022-CN
    * BIG5
    * EUC-TW
    * GB18030
    * HZ-GB-2312
  * Croatian:
    * UTF-8
    * ISO-8859-2
    * ISO-8859-13
    * ISO-8859-16
    * Windows-1250
    * IBM852
    * MAC-CENTRALEUROPE
  * Czech
    * UTF-8
    * Windows-1250
    * ISO-8859-2
    * IBM852
    * MAC-CENTRALEUROPE
  * Danish
    * UTF-8
    * IBM865
    * ISO-8859-1
    * ISO-8859-15
    * WINDOWS-1252
  * English
    * UTF-8
    * ASCII
  * Esperanto
    * UTF-8
    * ISO-8859-3
  * Estonian
    * UTF-8
    * ISO-8859-4
    * ISO-8859-13
    * ISO-8859-15
    * Windows-1252
    * Windows-1257
  * Finnish
    * UTF-8
    * ISO-8859-1
    * ISO-8859-4
    * ISO-8859-9
    * ISO-8859-13
    * ISO-8859-15
    * WINDOWS-1252
  * French
    * UTF-8
    * ISO-8859-1
    * ISO-8859-15
    * WINDOWS-1252
  * German
    * UTF-8
    * ISO-8859-1
    * WINDOWS-1252
  * Georgian
    * UTF-8
    * GEORGIAN-ACADEMY
    * GEORGIAN-PS
  * Greek
    * UTF-8
    * ISO-8859-7
    * WINDOWS-1253
    * CP737
  * Hebrew
    * UTF-8
    * ISO-8859-8
    * WINDOWS-1255
    * IBM862
  * Hindi
    * UTF-8
  * Hungarian:
    * UTF-8
    * ISO-8859-2
    * WINDOWS-1250
  * Irish Gaelic
    * UTF-8
    * ISO-8859-1
    * ISO-8859-9
    * ISO-8859-15
    * WINDOWS-1252
  * Italian
    * UTF-8
    * ISO-8859-1
    * ISO-8859-3
    * ISO-8859-9
    * ISO-8859-15
    * WINDOWS-1252
  * Japanese
    * UTF-8
    * ISO-2022-JP
    * SHIFT_JIS
    * EUC-JP
  * Korean
    * UTF-8
    * ISO-2022-KR
    * EUC-KR / UHC
    * Johab
  * Latvian
    * UTF-8
    * ISO-8859-4
    * ISO-8859-10
    * ISO-8859-13
  * Lithuanian
    * UTF-8
    * ISO-8859-4
    * ISO-8859-10
    * ISO-8859-13
  * Maltese
    * UTF-8
    * ISO-8859-3
  * Macedonian
    * UTF-8
    * ISO-8859-5
    * WINDOWS-1251
    * IBM855
  * Norwegian
    * UTF-8
    * IBM865
    * ISO-8859-1
    * ISO-8859-15
    * WINDOWS-1252
  * Polish:
    * UTF-8
    * ISO-8859-2
    * ISO-8859-13
    * ISO-8859-16
    * Windows-1250
    * IBM852
    * MAC-CENTRALEUROPE
  * Portuguese
    * UTF-8
    * ISO-8859-1
    * ISO-8859-9
    * ISO-8859-15
    * WINDOWS-1252
  * Romanian:
    * UTF-8
    * ISO-8859-2
    * ISO-8859-16
    * Windows-1250
    * IBM852
  * Russian
    * UTF-8
    * ISO-8859-5
    * KOI8-R
    * WINDOWS-1251
    * MAC-CYRILLIC
    * IBM866
    * IBM855
  * Serbian
    * UTF-8
    * ISO-8859-5
    * WINDOWS-1251
  * Slovak
    * UTF-8
    * Windows-1250
    * ISO-8859-2
    * IBM852
    * MAC-CENTRALEUROPE
  * Slovene
    * UTF-8
    * ISO-8859-2
    * ISO-8859-16
    * Windows-1250
    * IBM852
    * MAC-CENTRALEUROPE
  * Spanish
    * UTF-8
    * ISO-8859-1
    * ISO-8859-15
    * WINDOWS-1252
  * Swedish
    * UTF-8
    * ISO-8859-1
    * ISO-8859-4
    * ISO-8859-9
    * ISO-8859-15
    * WINDOWS-1252
  * Thai
    * UTF-8
    * TIS-620
    * ISO-8859-11
  * Turkish:
    * UTF-8
    * ISO-8859-3
    * ISO-8859-9
  * Ukrainian:
    * UTF-8
    * WINDOWS-1251
  * Vietnamese:
    * UTF-8
    * VISCII
    * Windows-1258
  * Others
    * WINDOWS-1252

## Installation

### Debian/Ubuntu/Mint

    apt-get install uchardet libuchardet-dev

### Mageia

    urpmi libuchardet libuchardet-devel

### Fedora

    dnf install uchardet uchardet-devel

### Gentoo

    emerge uchardet

### Mac

    brew install uchardet

  or

    port install uchardet

### Windows

Binary packages are provided in Fedora and Msys2 repositories. There may
exist other pre-built packages but I am not aware of them.
Nevertheless the library is very easily and quickly compilable under
Windows as well, so finding a binary package is not necessary.
Some did it successfully with the [CMake Windows
installer](https://cmake.org/download/) and MinGW. It should be possible
to use MinGW-w64 instead of MinGW, in particular to build both 32 and
64-bit DLL libraries).

Note also that it is very easily cross-buildable (for instance from a
GNU/Linux machine; [crossroad](https://pypi.org/project/crossroad/) may
help, this is what we use in our CI).

### Build from source

Releases are available from:
https://www.freedesktop.org/software/uchardet/releases/

If you prefer a development version, clone the git repository:

    git clone https://gitlab.freedesktop.org/uchardet/uchardet.git

The source can be browsed at: https://gitlab.freedesktop.org/uchardet/uchardet

    cmake .
    make
    make install

### Build with flatpak-builder

Here is a working "module" section to include in your Flatpak's json manifest:

```
"modules": [
    {
        "name": "uchardet",
        "buildsystem": "cmake",
        "builddir": true,
        "config-opts": [ "-DCMAKE_INSTALL_LIBDIR=lib" ],
        "sources": [
            {
                ...
            }
        ]
    }
]
```

### Build with CMake exported targets

uchardet installs a standard pkg-config file which will make it easily
discoverable by any modern build system. Nevertheless if your project also uses
CMake and you want to discover uchardet installation using CMake exported
targets, you may find and link uchardet with:

```
project(sample LANGUAGES C)
find_package ( uchardet )
if (uchardet_FOUND)
  add_executable( sample sample.c )
  target_link_libraries ( sample PRIVATE uchardet::libuchardet )
endif ()
```

Note though that we recommend the library discovery with `pkg-config` because it
is standard and generic. Therefore it will always work, even if we decided to
change our own build system (which is not planned right now, but may always
happen). This is why we advise to use standard `pkg-config` discovery.

Some more CMake specificities may be found in the [commit
message](https://gitlab.freedesktop.org/uchardet/uchardet/-/commit/d7dad549bd5a3442b92e861bcd2c5cda2adeea27)
which implemented such support.

## Usage

### Command Line

uchardet comes with a command line tool which obviously uses its own
library. It can be considered as a demo of `libuchardet` even though one
can find it very useful on its own right to inspect files.

```
uchardet Command Line Tool
Version 0.1.0

Authors: BYVoid, Jehan
Bug Report: https://gitlab.freedesktop.org/uchardet/uchardet/-/issues

Usage:
 uchardet [Options] [File]...

Options:
 -v, --version         Print version and build information.
 -h, --help            Print this help.
 -V, --verbose         Show all candidates and their confidence value.
 -w, --weight          Tweak language weights.
```

### Library

See [uchardet.h](https://gitlab.freedesktop.org/uchardet/uchardet/-/blob/master/src/uchardet.h)

## History

As said in introduction, this was initially a project of Mozilla to
allow better detection of page encodings, and it used to be part of
Firefox. If not mistaken, this is not the case anymore (probably because
nowadays most websites better announce their encoding, and also UTF-8 is
much more widely spread) and the original code has been abandoned.

It is to be noted that a lot has changed since the original
implementation, yet the base concept is still the same, basing detection
not just on encoding rules, but most importantly on analysis of
character statistics in languages.

Original code of `universalchardet` by Mozilla can still be retrieved from the
[Wayback machine](https://web.archive.org/web/20150730144356/http://lxr.mozilla.org/seamonkey/source/extensions/universalchardet/).

1. Mozilla code was extracted and packaged into a standalone library under
   the name `uchardet` by BYVoid in 2011, in a personal repository.
2. Starting 2015, I (i.e. Jehan) started contributing, "standardized"
   the output to be iconv-compatible, added various encoding/language
   support and streamlined generation of sources for new support of
   encoding/languages by using texts from Wikipedia as statistics source
   on languages through Python scripts. I soon became co-maintainer.
3. In 2016, `uchardet` became a freedesktop project.
4. Since 2015, the number of supported encoding continuously increased,
   in particular version 0.0.6 (2016) and especially 0.0.7 (2020) added
   a lot of new supported charset-language couples.
5. In 2021, I added language detection support.

## Techniques used

Techniques used originally by universalchardet are described at:
https://www-archive.mozilla.org/projects/intl/universalcharsetdetection

As said in the "*History*" section, the base algorithm is still there,
helping detection of charset with analysis of character statistics in
languages.

This is also why it could evolve in a quite efficient language detector.

Furthermore it does not use any dictionary, doesn't do semantics, or
nothing of the sort. The drawback of this is that it can be wrong
sometimes, especially on very short texts (a few words) when we don't
have enough data to differentiate while a word search in a dictionnary
could have done the trick. The advantages are that it makes it perform
much faster, with very small memory usage while still being extremely
performant on discriminating among a lot of charsets and languages when
your text is long enough.

## Supporting the project financially

I don't have a specific job around uchardet but I work on making Free
Software exclusively. In particular I develop
[GIMP](https://www.gimp.org/) and other Free Software within
[ZeMarmot](https://film.zemarmot.net/) project.
Thus uchardet is just one of the many FLOSS code I make.

So if you want to support my Free Software code, I suggest to donate to
*ZeMarmot* in one of these ways:

* Liberapay: https://liberapay.com/ZeMarmot/
* Patreon: https://www.patreon.com/zemarmot
* Tipeee: https://en.tipeee.com/zemarmot
* Other (Paypal, bank transfer…): https://film.zemarmot.net/en/donate

It might sound weird to fund a Libre Art animation film (Creative
Commons by-sa) to support the development of uchardet, but this is
exactly what happens if you do, as part of the donation go into salary
for me. And we need more funding to continue working on Free Software
for a living.

## Related Projects

Some of these are bindings of `uchardet`, others are forks of the same
initial code, which has diverged over time, others are native port in
other languages.
This list is not exhaustive and only meant as point of interest. We
don't follow the status for these projects.

  * [R-uchardet](https://cran.r-project.org/package=uchardet) R binding on CRAN
  * [python-chardet](https://github.com/chardet/chardet) Python port
  * [ruby-rchardet](http://rubyforge.org/projects/chardet/) Ruby port
  * [juniversalchardet](http://code.google.com/p/juniversalchardet/) Java port of universalchardet
  * [jchardet](http://jchardet.sourceforge.net/) Java port of chardet
  * [nuniversalchardet](http://code.google.com/p/nuniversalchardet/) C# port of universalchardet
  * [nchardet](http://www.conceptdevelopment.net/Localization/NCharDet/) C# port of chardet
  * [uchardet-enhanced](https://bitbucket.org/medoc/uchardet-enhanced) A fork of mozilla universalchardet
  * [rust-uchardet](https://github.com/emk/rust-uchardet) Rust language binding of uchardet
  * [libchardet](https://github.com/Joungkyun/libchardet) Another C/C++ API wrapping Mozilla code.

## Used by

* [mpv](https://mpv.io/) for subtitle detection
* [Notepad++](https://notepad-plus-plus.org/) for file encoding detection
* [Tepl](https://wiki.gnome.org/Projects/Tepl) (gedit…)
* [Nextcloud IOS app](https://github.com/nextcloud/ios)
* [Codelite](https://codelite.org)
* [QtAV](https://www.qtav.org/)
* …

## Licenses

* [Mozilla Public License Version 1.1](http://www.mozilla.org/MPL/1.1/)
* [GNU General Public License, version 2.0](http://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html) or later.
* [GNU Lesser General Public License, version 2.1](http://www.gnu.org/licenses/old-licenses/lgpl-2.1.en.html) or later.

See the file `COPYING` for the complete text of these 3 licenses.

## Code of Conduct

The `uchardet` project is hosted by [freedesktop.org](https://www.freedesktop.org/)
and as such follows its code of conduct. In other words, it means we
will treat anyone with respect and expect anyone to do the same.

Please read [freedesktop.org Code of Conduct](https://www.freedesktop.org/wiki/CodeOfConduct).

In case of any problem regarding abusive behavior in uchardet project,
please contact the maintainer (Jehan) or create a bug report (possibly
private if needed).
