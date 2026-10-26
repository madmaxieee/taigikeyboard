# Installation screenshot capture

Requested coverage: macOS, Windows and Linux installation steps in Traditional Chinese,
English, and Japanese. Save real screenshots in this directory, grouped by
platform and locale. Do not synthesize installer or operating-system screens.
Location: `media/screenshots/install/`.

1. Verify interactive desktop access and installed/released package versions.
2. Capture the full Windows workflow in each locale: opening the installer,
   security and SmartScreen prompts, installer screens,
   completion, and input-method setup/switching. Include prompts actually shown.
3. Capture macOS installer and input-source setup in each locale.
4. Capture Linux package installation and input-source setup in each available locale.
5. Inspect screenshots, document actual coverage and limitations, and remove temporary capture tasks.

Status: complete within the agreed scope. Captured and visually checked 73 PNGs from verified published desktop
3.8.0 packages. Windows has nine images per locale: SmartScreen blocked and expanded details,
installer ready,
progress and complete, language page, language options, installed keyboards and
input-method switcher. Linux has five Ubuntu 24.04/KDE/Fcitx5 images per locale.
Website and browser download screenshots are excluded by the user’s decision
on 2026-10-26. SmartScreen screens are retained with unnumbered filenames.
Capture tooling stays outside the repository.

UAC secure-desktop screenshots are excluded by the user's decision on
2026-10-26; keep the approval instructions as text. No further capture is pending.
Windows 10, Edge warnings and other Linux desktop/package-manager combinations
are outside the captured environment.

Original Windows language preferences and all three ordered input methods were
restored and verified after signing in: zh-Hant-TW, empty UI override, active
zh-TW UI. All 12 temporary capture tasks, four verified installer downloads and the
task-owned cumulative-update source downloads were removed. Existing unrelated
tasks, including TaigiKeyboard Update Check, were preserved. No app source changes, commit or push requested.

macOS follow-up completed on 2026-10-26: 31 real screenshots (10 per locale plus
one common English host input-menu image), from the signed/notarized published
3.8.0 package on macOS 27.0.1 Apple silicon. Includes all encountered
installer steps, optional destination selection, package cleanup prompt, Keyboard
settings, input-source search and addition, and input-menu switching. All three
installs succeeded without administrator authentication or a Gatekeeper block.

Original development app restored with an exact file-hash/symlink comparison;
code signature verified. Original preferred languages and input preferences
match the backup, apart from the input-source update timestamp; ABC is selected.
App-specific launch languages avoided global language changes and logout.
Temporary capture browser instances were closed; the user's browser was kept.
