# Third-party licenses

Desktop Scriptures is free software under the GNU General Public License,
version 3 or (at your option) any later version - see `LICENSE`. It is
built on, and ships with, the following works under their own licenses.

## Software

| Component | License | Source |
|---|---|---|
| Piper text-to-speech (`piper-tts`), including the bundled espeak-ng phonemizer | GPL-3.0-or-later | https://github.com/OHF-Voice/piper1-gpl |
| Qt for Python (PySide6) and the Qt libraries | LGPL-3.0 | https://doc.qt.io/qtforpython-6/ |
| ONNX Runtime | MIT | https://github.com/microsoft/onnxruntime |
| NumPy | BSD-3-Clause | https://numpy.org |
| Python | Python Software Foundation License | https://www.python.org |
| SQLite | Public domain | https://sqlite.org |

The LGPL lets you replace the Qt libraries with your own build: in the snap
they are ordinary shared libraries alongside the app.

## Voices (Listen)

Voices aren't included with the app. Listen downloads the ones you choose
(Menu → Voice → Download or Remove Voices...) directly from
https://huggingface.co/rhasspy/piper-voices (MIT, as a collection). Each
voice was trained on a dataset with its own terms:

| Voice | Dataset | Dataset license |
|---|---|---|
| American English (Male) - `en_US-lessac-medium` | Lessac / Blizzard 2013 | Research license from Lessac Technologies: https://www.cstr.ed.ac.uk/projects/blizzard/2013/lessac_blizzard2013/license.html |
| American English (Female) - `en_US-hfc_female-medium` | Hi-Fi CAPTAIN (NICT) | CC BY-NC-SA 4.0 (non-commercial) |
| British English (Male) - `en_GB-alan-medium` | Mycroft mimic3 voice of Alan Pope | Copyright Mycroft AI: https://github.com/MycroftAI/mimic3-voices |
| British English (Female) - `en_GB-cori-medium` | LibriVox recordings | Public domain |

## Data

| Data | License or terms | Source |
|---|---|---|
| Strong's Hebrew and Greek dictionaries (Open Scriptures edition) | CC BY-SA 4.0 | https://github.com/openscriptures/strongs |
| STEP Bible short word meanings (Tyndale House, Cambridge) | CC BY 4.0 | https://www.STEPBible.org |
| Scripture text | Courtesy of the lds-scriptures project | https://github.com/beandog/lds-scriptures |
| Journal of Discourses and the Inspired Version (JST) | Public domain scans | https://archive.org |
| The Apocrypha (King James Version, 1769 text) | Public domain, courtesy of the CrossWire Bible Society and eBible.org | https://ebible.org/find/details.php?id=eng-kjv |
| General Conference citation data | Courtesy of BYU's Scripture Citation Index | https://scriptures.byu.edu |
| Book of Mormon name meanings | This project's own summaries, each linked to BYU's Book of Mormon Onomasticon | https://onoma.lib.byu.edu |

The CC BY-SA and CC BY licenses apply to that data, not to the app's code.
