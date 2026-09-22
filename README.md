# Desktop Scriptures

[![desktop-scriptures](https://snapcraft.io/desktop-scriptures/badge.svg)](https://snapcraft.io/desktop-scriptures)

A desktop reader for the Bible, Book of Mormon, Doctrine and Covenants,
Pearl of Great Price, Journal of Discourses, Lectures on Faith, and the
Joseph Smith Translation. The core reading and study experience works
fully offline - personal notes, tags, verse highlighting, keyword
search, a Topical Guide, General Conference citations, a Scripture of
the Day banner, a reading streak, a Resume Reading history of your last
5 chapters, a choice of accent colors, and cloud-folder sync across your
own devices (via whatever cloud client - Nextcloud, OneDrive, Google
Drive, or similar - already keeps a folder synced on your machine, so
the app itself never talks to the network for this).

A handful of landing-page extras are opt-in and off by default, only
reaching the network once you turn them on: AI-assisted search (ask a
question in your own words - and refine it conversationally with
follow-ups - to get pointed at real, matching scripture, using your own
AI endpoint), a Church News headline, a Come Follow Me helper showing
this week's lesson, and an Inspirational Message featuring whatever's
currently on churchofjesuschrist.org's own homepage.

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

![Landing page with the Inspirational Message, Come Follow Me, Scripture of the Day, and Church News boxes](docs/screenshots/landing.png)

![A chapter open with a highlight, chapter tags/note, and a verse note](docs/screenshots/chapter.png)

![AI-assisted search answering a natural-language question, then narrowed with a follow-up](docs/screenshots/ai-search.png)

## Install

Desktop Scriptures is published on the Snap Store:

```
sudo snap install desktop-scriptures
```

## TODO

Features under consideration for future versions:

- [x] Reading history (v1.3 - Resume Reading now shows your last 5 chapters, most recent first)
- [x] AI-assisted search (v2.0 - ask a question in your own words in the search bar, then refine it conversationally with follow-ups, and get pointed at real, matching scripture; opt-in, bring-your-own AI endpoint - OpenAI, another compatible provider, or a locally-run server; see the AI Integration menu - v2.0.1 also surfaces any General Conference talks already known to cite a suggested verse)
- [ ] Talk prep helper (uses AI to suggest supporting scriptures, talks, etc.)
- [ ] Apocrypha?
- [ ] Wiki
- [x] JST (v1.3)
- [x] Topical Guide (v2.0.1 - expanded from 25 to 46 topics)
- [x] Syncing capability (v2.0 - point at a folder already kept in sync by Nextcloud, OneDrive, Google Drive, Dropbox, or similar)
- [x] Theme enhancements (v2.0 - a choice of accent colors, loosely inspired by Ubuntu's Yaru accent picker)
- [ ] Listen to the scriptures - voice capability
- [x] CFM helper/reminder (v2.1.1 - an opt-in landing-page box showing this week's Come Follow Me lesson, off by default like Church News; the reminder half of this item is still open, see General Conference reminder below)
- [x] Church News button (v2.0.9 - an opt-in landing-page box showing the latest headline from Church News' own RSS feed, off by default like AI-assisted search)
- [ ] Linguistics references
- [ ] Archaeological references
- [ ] Family history reminder
- [ ] Journal/Diary feature
- [ ] General Conference reminder
- [ ] General Conference Talk auto updater
- [ ] Embedded webui for talk references, etc. 
