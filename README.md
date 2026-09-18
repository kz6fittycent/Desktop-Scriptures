# Desktop Scriptures

[![desktop-scriptures](https://snapcraft.io/desktop-scriptures/badge.svg)](https://snapcraft.io/desktop-scriptures)

A desktop reader for the Bible, Book of Mormon, Doctrine and Covenants,
Pearl of Great Price, Journal of Discourses, Lectures on Faith, and the
Joseph Smith Translation - fully offline, with personal notes, tags,
verse highlighting, keyword search, a Topical Guide, General Conference
citations, a Scripture of the Day banner, and a reading streak.

This is an **unofficial** application, not produced by or affiliated
with The Church of Jesus Christ of Latter-day Saints, or with Community
of Christ. Scripture text courtesy of the [beandog/lds-scriptures](https://github.com/beandog/lds-scriptures)
project; Journal of Discourses and Joseph Smith Translation (published
as the "Inspired Version") text courtesy of their public-domain scans on
[archive.org](https://archive.org) (Journal of Discourses discourse
metadata cross-referenced from FAIR's index); General Conference
citation data courtesy of [BYU's Scripture Citation Index](https://scriptures.byu.edu).
The Topical Guide is Desktop Scriptures' own correlation of its local
scripture text and that same citation index (see
`scripts/build_topical_guide.py`) - not a copy of the Church's own,
separately-copyrighted Topical Guide.

## Screenshots

![Landing page with the Scripture of the Day banner](docs/screenshots/landing.png)

![A chapter open with a highlight, chapter tags/note, and a verse note](docs/screenshots/chapter.png)

## Install

Desktop Scriptures is published on the Snap Store:

```
sudo snap install desktop-scriptures
```

## TODO

Features under consideration for future versions:

- [ ] Complete reading history
- [ ] AI integration to help provide full context of chapter/verse/doctrine based on Conference talks, Discourses, etc.
- [ ] Talk prep helper (uses AI to suggest supporting scriptures, talks, etc.)
- [ ] Amount of time spent in scriptures (hours/minutes)
- [ ] Apocrypha?
- [ ] Wiki
- [x] JST (v1.3 - 61 of 66 books imported; Song of Solomon was never translated in this edition)
- [ ] JST: 2 John, 3 John, Jude, and Revelation - skipped in v1.3 because this specific scan has pages interleaved out of order across that section; needs either a second source for just those books or manual reconstruction (see scripts/import_inspired_version.py)
- [x] Topical Guide (v1.3 - 25 major topics, correlated from the app's own scripture text and General Conference citation index; see scripts/build_topical_guide.py)
- [ ] P2P syncing capability
