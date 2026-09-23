# Seeing the System — web slideshow

The two-day workshop deck as a website. Built to be projected: it scales to any
screen, works with a clicker, and has a presenter view with your speaker notes.

## Run it locally

Browsers won't load the slide files if you double-click `index.html`.
Start a small web server in this folder instead:

    python3 -m http.server 8000

Then open http://localhost:8000.

## Put it online

**Netlify:** drag this folder onto https://app.netlify.com/drop. Done.
Or connect the Git repo; there is no build command and the publish directory is the repo root (`netlify.toml` already says so).

**GitHub Pages:** push this folder to a repo, then Settings → Pages → Deploy from a branch → `main` / root.
The empty `.nojekyll` file must stay; it stops GitHub from hiding folders.

## Presenting

| Key | Does |
|---|---|
| → Space PgDn / ← PgUp | Next / previous (clickers send these) |
| Home / End | First / last slide |
| a number, then Enter | Jump to that slide |
| F | Full screen |
| T | Light or dark |
| C | Next colour palette (Shift+C goes back) |
| O | All slides, click one to jump |
| N | Speaker notes on this screen (for rehearsal) |
| P | Presenter view in a new window: current slide, next slide, notes, timer. Put it on your laptop, the main window on the projector. They stay in sync. |
| B | Black screen; any key brings it back |
| H | Include or skip hidden slides |
| ? | This list |

Useful links: `index.html#/42` opens slide 42, `?palette=sage&theme=dark` picks a look, `?all` includes hidden slides.

## Palettes

Four palettes, each with a light and a dark mode. Pick one from the palette button in the controls, or press C.
Your choice is remembered on that browser, and the presenter window follows the main one.

| Palette | Light | Dark |
|---|---|---|
| Terracotta | the original deck, untouched | clay softened so it doesn't glare on charcoal |
| Sage | warm white, muted green | near-black green, pale sage |
| Indigo | cool paper, ink blue | deep navy, periwinkle |
| Graphite | neutral greys, teal | charcoal, soft teal |

Palettes recolour everything drawn on the slides — backgrounds, panels, text, rules, accents.
Pictures (the NotebookLM illustrations, photos) keep their own colours.
Palettes live in section 2 of `assets/deck.css`; to add one, copy a light and a dark block and add an entry to `PALETTES` in `assets/deck.js`.
To make a PDF handout, open the deck and print to PDF (Chrome: Save as PDF, background graphics on).

## Adding, removing and reordering slides

The show order lives in one file: **`slides/manifest.js`**.

    window.DECK_MANIFEST = [
      { file: "s001-seeing-the-system.html" },
      { file: "my-new-slide.html" },                 // ← inserted here
      { file: "s011-what-is-a-system.html", hidden: true },
      ...
    ];

- **Insert:** create a file in `slides/`, add a line where it should appear.
- **Hide without deleting:** add `hidden: true`.
- **Reorder:** move lines. File names don't have to match the order — the `s001…` prefixes only record where a slide sat in the original PowerPoint.
- **Delete:** remove the line (and the file, if you like).

### Writing a new slide

Copy a starter from `slides/templates/` into `slides/`, rename it, and edit the text:

| Template | Use it for |
|---|---|
| `section.html` | Dark divider with a numeral (like "II · The Constraint") |
| `statement.html` | One big sentence, centred |
| `bullets.html` | Heading, framing line, a few points |
| `cards.html` | The three-panel lab brief ("What you do / What you produce / How you know you're done") |
| `image.html` | A full-slide picture — drop the image in `media/` |

These use the deck's fonts and colours and switch themes automatically.
Every slide is a `<section class="slide">` drawn on a 1920 × 1080 canvas, so size things for that and they'll scale.
Speaker notes go in `<aside class="notes">` inside the section.

### Editing a converted slide

The original slides were converted with every element positioned exactly as in PowerPoint.
Open the file, find the text, change it. Colours appear as `var(--t-2C2620,#2C2620)`:
the hex is the original colour, and the dark theme remaps it (see section 5 of `assets/deck.css`).

## Bringing in slides from PowerPoint

Copying a slide file does not restyle it: each converted slide keeps its own layout and colours.
Slides built in the deck's own colours (the cream/terracotta house style) follow the palettes automatically, because the palettes remap those exact colours.
Slides in other colours come across as they are.

To convert a new PowerPoint (say, a few extra slides for day three) without touching anything already here (needs `python-pptx` and `Pillow`):

    pip install python-pptx pillow
    python3 tools/convert_pptx.py day3.pptx . --prefix day3-

This writes `slides/day3-001-….html` etc. and their images, then prints the lines to paste into `slides/manifest.js`.
Use a different prefix each time so names never collide.

Running it **without** `--prefix` rebuilds the whole original deck and overwrites `slides/s*.html`, its images and the manifest
(then run `python3 tools/build_manifest.py .`). Only do that if the original PowerPoint itself has changed.

## What's where

    index.html            the page
    assets/deck.css       layout, themes, controls, the new-slide styles
    assets/deck.js        navigation, overview, notes, presenter view
    assets/fonts/         Gelasio and Carlito (stand-ins for Georgia and Calibri)
    slides/manifest.js    the running order
    slides/*.html         one file per slide
    slides/templates/     starters for new slides
    media/                images
    tools/                the converter, for rebuilding from PowerPoint
