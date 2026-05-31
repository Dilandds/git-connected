## What is actually wrong

The Technical Overview button is not broken because of card spacing anymore. The screenshot shows a Qt painting/layout issue inside the button itself: the text is vertically clipped and the rounded corners/border do not render like the other upload buttons.

## Why it happened

- The button is using the shared `uploadBtn` stylesheet from `ui/styles.py`.
- That shared style includes large vertical padding (`12px` top and bottom) plus Qt stylesheet margins (`margin-top: 2px`, `margin-bottom: 14px`).
- The widget is only given `setMinimumHeight(50)`, not a real fixed safe height.
- For this specific label, `Upload Image / PDF / .ecto`, Qt needs more internal height than the shorter `Upload Drawing` button.
- Because the available paint area is too small, Qt clips the top of the bold text and the border radius looks flattened/wrong.

## Fix plan

1. Change only `ui/technical_sidebar.py` for this button.
2. Keep the surrounding card spacing exactly as it is, since you said the spaces are correct.
3. Give the Technical Overview upload button a dedicated object name, for example `technicalUploadBtn`, so it does not inherit the problematic shared `uploadBtn` margin/padding assumptions.
4. Apply a dedicated stylesheet with the same blue gradient, border, font weight, and visual style, but with safe internal metrics:
   - no Qt stylesheet margins inside the button
   - slightly smaller vertical padding
   - a real fixed/minimum height around `56px`
   - matching rounded radius around `22px`
5. Keep the existing shadow and click behavior unchanged.
6. Optionally set the text from the translation key immediately (`t("technical.upload_btn")`) instead of a hardcoded string, so startup and language refresh use the same label.

## Expected result

The Technical Overview upload button will visually match the other upload buttons, but it will no longer clip the letters or flatten the rounded border because its own style will reserve enough paintable height for the longer text.