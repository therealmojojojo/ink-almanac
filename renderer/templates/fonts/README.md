# Fonts

Self-host the font files here. They are not committed to the repo.

Required files (download from Google Fonts / IBM Plex):

- `Fraunces[opsz,wght].woff2` — variable, roman (opsz 9–144, wght 100–900)
- `Fraunces-Italic[opsz,wght].woff2` — variable, italic
- `IBMPlexMono-Regular.woff2`
- `IBMPlexSans-Light.woff2`
- `IBMPlexSans-Regular.woff2`

See `renderer/templates/shared/fonts.css` for the `@font-face` declarations.

If these files are missing, templates degrade to system serif/mono/sans stacks.
`npm run lint:fonts` flags missing files and missing Romanian diacritic coverage.
