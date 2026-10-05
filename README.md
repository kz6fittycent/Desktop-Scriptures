# Desktop Scriptures

[![desktop-scriptures](https://snapcraft.io/desktop-scriptures/badge.svg)](https://snapcraft.io/desktop-scriptures)

An offline desktop reader for the Bible, Book of Mormon, Doctrine and
Covenants, Pearl of Great Price, Journal of Discourses, Lectures on Faith,
and the Joseph Smith Translation. The Apocrypha (KJV) and Other Ancient
Texts (1 Enoch and the Book of Jasher), which aren't part of the Standard
Works, can be switched on under **Menu → Additional Books**.

## Features

- **Study:** notes, tags, verse highlighting, keyword search, a Topical Guide, and a searchable Journal with one entry per day.
- **Cross-references:** 610 hand-checked parallel passages, each tagged with the doctrine it teaches, plus any you add yourself.
- **Word Study:** the Hebrew, Aramaic, and Greek word behind any word of the Bible (right-click it), and what Book of Mormon names may mean, each labeled by how sure that meaning is. In Book of Mormon chapters, names and dates are links; dates open a card placing them in Israel's calendar.
- **Citations:** the General Conference talks and Liahona articles that cite each verse, kept current by a weekly update.
- **Listen:** any chapter read aloud, verse by verse, in a choice of four voices you download once.
- **Sync:** your study across your own devices, through a folder your cloud client already syncs.
- **Opt-in extras:** AI-assisted search using an AI service you choose, Church News, Come Follow Me, an Inspirational Message, and reminders for General Conference, temple recommend renewal, and family history.

A Welcome window on first launch walks through the optional parts.

## Privacy

The app reads and studies fully offline. It contacts nothing until you switch a feature on, with one exception: about once a day it checks this project's GitHub for new talk and article citations (switch it off under **Menu → View → Download New Talks and Articles**).

## Sources and credits

This is an **unofficial** application, not produced by or affiliated with The Church of Jesus Christ of Latter-day Saints, or with Community of Christ.

- Scripture text: [beandog/lds-scriptures](https://github.com/beandog/lds-scriptures).
- Journal of Discourses and Joseph Smith Translation ("Inspired Version"): public-domain scans on [archive.org](https://archive.org); discourse details cross-checked with FAIR's index.
- Apocrypha (KJV 1769 text, public domain): the CrossWire Bible Society and [eBible.org](https://ebible.org/find/details.php?id=eng-kjv).
- 1 Enoch (R. H. Charles, 1917): [Project Gutenberg](https://www.gutenberg.org/ebooks/77935) and Distributed Proofreaders. Book of Jasher (1840): [Wikisource](https://en.wikisource.org/wiki/Sefer_Ha-yashar,_or,_the_Book_of_Jasher_(1840)). Both public domain.
- General Conference citations: [BYU's Scripture Citation Index](https://scriptures.byu.edu). Liahona citations: each article's own scripture links on [churchofjesuschrist.org](https://www.churchofjesuschrist.org). Both are metadata only (title, speaker, date, link); the app links to talks and articles, never copies them.
- The Topical Guide (`scripts/build_topical_guide.py`) and cross-references (`scripts/build_cross_references.py`) are this project's own work, checked against the app's text. The Topical Guide is not the Church's copyrighted one.
- Strong's numbers for each word of the KJV: the CrossWire Bible Society and [eBible.org](https://ebible.org/find/details.php?id=eng-kjv) (public domain).
- Lexicons: Strong's dictionaries in [Open Scriptures](https://github.com/openscriptures/strongs)' corrected editions (CC BY-SA, for the lexicon data only) and word meanings from [STEP Bible](https://www.STEPBible.org) (Tyndale House, Cambridge; CC BY 4.0).
- Book of Mormon name meanings: this project's own summaries of the proposals in BYU's [Book of Mormon Onomasticon](https://onoma.lib.byu.edu), linked rather than copied.

## Help and About

The [wiki](https://github.com/kz6fittycent/Desktop-Scriptures/wiki) is the user guide; in the app, **Menu → Help (Wiki)...** links to each page. **Menu → About** shows the version, the license (GPL-3.0 - **View License...** shows it in full, offline, along with the licenses of the software and data the app includes, and of the downloadable voices), and credits.

## Screenshots

![Landing page with the Inspirational Message, Come Follow Me, Scripture of the Day, and Church News boxes](docs/screenshots/landing.png)

![A chapter open with a highlight, chapter tags/note, and a verse note](docs/screenshots/chapter.png)

![AI-assisted search answering a natural-language question, then narrowed with a follow-up](docs/screenshots/ai-search.png)

![A Journal entry linked to Alma 32:21, with Previous/Next Day navigation](docs/screenshots/journal.png)

![2 Nephi 3 being read aloud, with the current verse highlighted and Pause/Stop controls](docs/screenshots/listen.png)

![Doctrine and Covenants 6's Cross-references tab, showing three parallel passages each tagged with the doctrine at stake](docs/screenshots/cross-references.png)

## Install

**Linux:** Desktop Scriptures is published on the Snap Store:

```
sudo snap install desktop-scriptures
```

**Windows 11 and macOS (Apple Silicon):** in testing. Every change on
`main` produces a test build - see the newest issue labeled
[`desktop-testing`](https://github.com/kz6fittycent/Desktop-Scriptures/issues?q=label%3Adesktop-testing)
for download links and how to open them. They aren't code-signed yet, so the
first launch takes one extra click on each system. Releases (from a version
tag) go on the [Releases page](https://github.com/kz6fittycent/Desktop-Scriptures/releases).
Packagers are welcome: Homebrew, Winget, and Chocolatey packages would be
maintained by the community. See [`packaging/README.md`](packaging/README.md).

## Roadmap

### Next

- [ ] Talk prep helper: an AI-assisted chat that suggests scriptures, talks, and articles for a talk or lesson, built on the study index
- [ ] Windows and macOS out of testing into regular releases, with code signing if there's demand

### v3.0

The goal: ask about a word, a name, or a place and get a clear, sourced answer, even with a small AI model on your own computer. Done so far: Hebrew and Greek word meanings, the exact word behind each word of the Bible (and the JST) through a word-by-word Strong's-tagged text, Book of Mormon names and their links in the text, and Book of Mormon dates in Israel's calendar.

- [ ] Short answers drawn only from the sources found, with every statement cited
- [ ] Geography for all the Standard Works: Bible places and maps, and the Book of Mormon geography models shown side by side as their proponents' theories (the Church takes no official position)
- [ ] Archaeological references
- [ ] Optional content packs, downloaded on demand

Every source's license is checked before anything is imported. Copyrighted works are linked and summarized, not copied.

## License

Copyright (C) 2026 kz6fittycent

Desktop Scriptures is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any
later version. It is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; see [`LICENSE`](LICENSE) for details.

Versions up to and including 2.2.8 were released under the MIT License.
The software and data the app includes, and the voices it can download,
carry their own licenses -
see [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md).
