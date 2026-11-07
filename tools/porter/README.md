# Board Game Porter

Turn photos or scans of a board game you own into a Tabletop Club asset pack:
a 3D board, cards with their real backs, and round or square tokens, sized in
real centimetres. Then play it on the computer, alone or online with friends.

## Use it

1. Make a folder for the game and put your pictures in it:

   ```
   My Game/
     board.jpg                 the board, shot from straight above
     cards/Events/*.jpg        one picture per card front
     cards/Events/back.jpg     the card back
     tokens/round/*.jpg        coins, chips, round markers
     tokens/square/*.jpg       square tiles and markers
     backs/<same name>.jpg     the other side of a two-sided token
     porter.toml               optional sizes (copy example.toml)
   ```

   Phone photos are fine (iPhone .heic too). Lay each piece on a plain table
   that is a different colour from the piece. The porter crops each photo
   down to the piece and straightens tilts of up to 20 degrees. Shoot from
   straight above, because it does not fix a slanted camera angle.

2. Run it:

   ```
   python3 tools/porter/porter.py "My Game" --install
   ```

3. Open Tabletop Club. Your game is in the Objects menu under its own pack
   name. Set the table up once, then use Menu > Save game so the whole
   game loads in one click next time.

Needs Python 3.11+ with Pillow and numpy (`pip install pillow numpy`).

## What it makes

| You give it | You get |
|---|---|
| board photo | `boards/<name>.obj` - a box with the picture on top, real width |
| card photos or a card sheet | `cards/` - each card with its deck's back |
| round token photos | `tokens/cylinder/` - chips with front and back faces |
| square token photos | `tokens/cube/` - tiles with front and back faces |

The pack is for your own copy of the game. Don't share packs made from
copyrighted art.
