

# Passcode Warning & Recovery Hints

## What Changes

Two small text updates to the existing `PasscodeDialog` in `ui/passcode_dialog.py`:

1. **Set mode** — Add a warning below the hint text:
   - *"⚠ Important: This passcode can only be reset from this machine's application. If you lose access to this machine, the passcode cannot be recovered."*

2. **Enter mode** — After a wrong passcode attempt, show a recovery hint below the error:
   - *"If you've lost the passcode, please contact the person who created this file to reset it from their machine."*

## Technical Details

**File: `ui/passcode_dialog.py`**

- **Set mode (line 81)**: Change the hint label text to include the machine-only reset warning:
  ```python
  hint = QLabel(
      "This passcode will be required to edit the .ecto file.\n"
      "Anyone can still view the file without a passcode.\n\n"
      "⚠ Important: This passcode can only be reset from this\n"
      "machine's application. Keep it safe."
  )
  ```

- **Enter mode (line 149)**: After "Incorrect passcode. Try again.", add a persistent recovery hint label (styled in muted text, always visible in enter mode) below the status label:
  ```python
  recovery_hint = QLabel(
      "Lost passcode? Ask the file creator to reset it from their machine."
  )
  ```
  Styled with `text_secondary` color, smaller font size (10px), centered.

**Single file change, no new dependencies.**

