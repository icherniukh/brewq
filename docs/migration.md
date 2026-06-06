# Migration Notes

## Provenance

Original implementation source:

- `/Users/ivan/proj/dotfiles-stow/dot_scripts/executable_bsx`

Original guide source:

- `/Users/ivan/proj/ccconfig/guides/brew-search-rich-smart.md`

Original tracker item:

- `/Users/ivan/.beads`, issue `TG-eio`
- Title: `bsx Python rewrite with column system`

Local tracker item:

- `brewq-d9n`
- Title: `Implement brewq Python CLI from transferred bsx scope`

## What Was Migrated

- The current zsh implementation was copied to `legacy/bsx-prototype.zsh`.
- The guide content was consolidated into `README.md`, `docs/vision.md`, `docs/stack.md`, and `docs/roadmap.md`.
- The original global tracker item was transferred into this repo as local beads issue `brewq-d9n`.

## Cleanup Later

Do not delete the dotfiles copy until the Python CLI can replace it in the live shell setup.

After replacement:

- Update dotfiles to call the packaged `brewq`.
- Remove or archive `dot_scripts/executable_bsx`.
- Replace `ccconfig/guides/brew-search-rich-smart.md` with a pointer to this project, or remove it if this repo becomes the canonical home.
