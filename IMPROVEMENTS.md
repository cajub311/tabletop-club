# Ideas for this copy of Tabletop Club

Goal: bring any board game we own onto the computer quickly, with every
board, card and token, and play it in 3D.

## Done

- **Board Game Porter** (`tools/porter/`): photos or scans go in, and a ready
  asset pack comes out. It crops and straightens each photo, cuts card sheets
  into single cards, makes the board a 3D model at its real size, and builds
  two-sided round and square tokens. It reads iPhone .heic photos. Tested in
  Tabletop Club v0.1.5: every piece in the test pack loaded with no errors.

## Next, most useful first

1. **Print-and-play PDFs**: many games publish free PDF sheets. Turn each PDF
   page into a card sheet (needs poppler's `pdftoppm` or PyMuPDF).
2. **Slanted photo fix**: correct the camera angle for photos taken at a slant
   by finding the 4 corners. That needs OpenCV.
3. **Auto table setup**: write the game's `.tc` save file so the board,
   decks and tokens start in place in one click. The format is a Godot binary
   Variant, zstd-compressed, so this one is harder.
4. **Custom dice**: d6 faces from 6 photos (the cube texture already matches,
   it just needs `face_values`).
5. **Standees and meeples**: a cut-out picture on a little stand, or simple
   meeple shapes in each player colour.
6. **In-game "Import from photos" button**: run the porter from the game's
   own menu, so you never need the terminal.
7. **Rules helpers** (optional per game): turn order marker, auto-deal hands,
   score track counter. Tabletop Club is a sandbox, so these would be small
   add-ons, not full rule checks.
8. **AI opponent**: much later, and only for simple games.

Personal game packs stay out of git (`.gitignore`): they hold the publishers'
art.
