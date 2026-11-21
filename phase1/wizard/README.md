# `apps.list` — the first-boot app catalog

The wizard **code** lives in its own repo (`github.com/r4-ndm/app-wiz4rd`) and
ships into the ISO as a sha-pinned tarball (`iso/vendor/`, `APP_WIZ4RD_SHA256`
in `iso/build.sh`). Change the wizard there.

What stays here is the **catalog**, because `iso/build.sh` copies it to
`/etc/syntropia/apps.list` and `iso/tests/test_ssh_setup.py` asserts against it.

Format — one app per line, pipe-separated:

```
category|display name|package|short description[|aliases]
```

- `package` is a pacman repo **or** AUR package name (yay resolves either).
- `package` may be an `https://` URL — the wizard then creates a PWA-style
  desktop launcher instead of installing anything.
- The optional 5th field is a comma-separated alias list, shown dimmed and
  searchable in the picker.
- Category is a section header; rows keep file order.

Adding an app is a one-line edit. Keep entries alphabetised within a category,
and keep `Remote|SSH Setup|syntropia-ssh-setup` — a test pins it.
