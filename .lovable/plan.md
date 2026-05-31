## Goal
Make the "Upload Image / PDF / .ecto" button in Technical Overview look and space identically to the "Upload Drawing" button in Drawing Scale (the rounded glossy pill shown in the Drawing Scale screenshot).

## Root cause
`ui/scale_sidebar.py` uses the shared `get_button_style("uploadBtn")` from `ui/styles.py` (radius 22px, padding 12px 20px, no side margins, `setMinimumHeight(50)`).

`ui/technical_sidebar.py` instead defines its own inline stylesheet on `uploadTechBtn` with different metrics:
- `setFixedHeight(56)` instead of `setMinimumHeight(50)`
- `border-radius: 999px`, `padding: 10px 32px`
- Extra `margin-left/right: 12px` (insets the button inside the card)

That mismatch is what makes it appear more rectangular and narrower than the Drawing Scale pill.

## Change
In `ui/technical_sidebar.py`, replace the inline-styled `uploadTechBtn` block with the same setup the scale sidebar uses:

- `self.upload_btn.setObjectName("uploadBtn")` (so the shared global stylesheet applies)
- `self.upload_btn.setMinimumHeight(50)` (drop `setFixedHeight(56)`)
- `self.upload_btn.setStyleSheet(get_button_style("uploadBtn"))`
- Keep `setAttribute(Qt.WA_StyledBackground, True)`, the pointing cursor, and the existing card shadow call
- Remove the custom `qlineargradient` stylesheet and the extra left/right margins

No other layout changes — the surrounding `upload_card` / `upload_card_layout` already mirrors `scale_sidebar.py`, so spacing inside the card and around the title will match automatically once the button metrics align.

## Files
- `ui/technical_sidebar.py` — swap the button styling block (≈30 lines) for the shared style.
