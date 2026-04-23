# doctest

Vendored at `doctest.h` (single header). Drop the latest release from
https://github.com/doctest/doctest/releases/latest into this directory as
`doctest.h`. CI / first build:

```bash
curl -L \
  https://raw.githubusercontent.com/doctest/doctest/master/doctest/doctest.h \
  -o firmware/test/third_party/doctest/doctest.h
```

The file is intentionally not committed; it's a build prerequisite like
Playwright's Chromium binary.
