//! When a committed word earns the auto-space trailing space — the one copy
//! the three desktops run (behavioural invariant §23,
//! `INVARIANT_AUTO_SPACE_PUNCTUATION_SWAP`). Which punctuation attaches is
//! the engine's (`engine::is_attaching_punctuation`), as on every platform.

use crate::settings::InputMode;

/// True when this commit earns a trailing space at all — the same gate every
/// insertion site and the punctuation swap read. `wrote_romanization` comes
/// from whatever resolved the string: the engine for a candidate
/// (`CommitResolution.earns_auto_space`), [`raw_preedit_writes_romanization`]
/// for the preedit itself.
pub fn is_gate_active(is_auto_space_enabled: bool, wrote_romanization: bool) -> bool {
    is_auto_space_enabled && wrote_romanization
}

/// Whether committing the preedit AS TYPED writes romanization — the
/// literal-commit chord and a mid-composition punctuation commit with no
/// highlighted candidate (or with a pending tail after a prefix pick).
///
/// TPS writes glyphs as typed, which take no spacing. A `match` rather than
/// `matches!`, so a new input mode has to decide here.
/// CROSS-PLATFORM INVARIANT — Android mirrors it in `android/.../CandidateClickHandler.kt`
/// `rawPreeditWritesRomanization(isTPSLayout:)`.
pub fn raw_preedit_writes_romanization(input_mode: InputMode) -> bool {
    match input_mode {
        InputMode::Tl | InputMode::Poj => true,
        InputMode::Tps => false,
    }
}

/// Whether the text a commit just wrote should be followed by a space —
/// judged on the actual document string; a trailing hyphen (a syllable
/// about to be continued) suppresses it.
pub fn should_append_space(document_text: &str) -> bool {
    !document_text.is_empty() && !document_text.ends_with('-')
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::is_attaching_punctuation;

    #[test]
    fn the_attaching_set_is_the_engines() {
        // trace: engine `phonetics::punctuation::ATTACHING` holds `？` and
        // `」`, not the opener `「` or a letter; the full roster is pinned
        // there.
        assert!(is_attaching_punctuation("？"));
        assert!(is_attaching_punctuation("」"));
        assert!(!is_attaching_punctuation("「"));
        assert!(!is_attaching_punctuation("a"));
    }

    #[test]
    fn the_gate_follows_whether_the_commit_wrote_romanization() {
        // trace: `is_gate_active` = enabled AND wrote_romanization — on only
        // for (true, true).
        assert!(!is_gate_active(false, true));
        assert!(!is_gate_active(false, false));
        assert!(is_gate_active(true, true));
        assert!(!is_gate_active(true, false));
    }

    #[test]
    fn a_fresh_install_has_the_gate_off_for_romanization() {
        // trace: the shipped default is OFF on every platform
        // (`keys::IS_AUTO_SPACE_ENABLED` says why).
        let document = crate::settings::SettingsDocument::default();
        let enabled = document.bool(&crate::settings::keys::IS_AUTO_SPACE_ENABLED);
        assert!(!is_gate_active(
            enabled,
            raw_preedit_writes_romanization(InputMode::Tl)
        ));
    }

    #[test]
    fn committed_word_earns_the_space_but_a_trailing_hyphen_suppresses_it() {
        assert!(should_append_space("guá"));
        assert!(!should_append_space("guá-"));
        assert!(!should_append_space(""));
    }

    #[test]
    fn a_tps_preedit_written_as_typed_is_not_romanization() {
        assert!(raw_preedit_writes_romanization(InputMode::Tl));
        assert!(raw_preedit_writes_romanization(InputMode::Poj));
        assert!(!raw_preedit_writes_romanization(InputMode::Tps));
    }
}
