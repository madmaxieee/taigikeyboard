//! When a committed word earns the auto-space trailing space — the one copy
//! the three desktops run (behavioural invariant §23,
//! `INVARIANT_AUTO_SPACE_PUNCTUATION_SWAP`). Whether a commit wrote
//! spaceable romanization is the engine's verdict
//! (`CommitResolution.earns_auto_space`), as is which punctuation attaches
//! (`engine::is_attaching_punctuation`), as on every platform.

/// True when this commit earns a trailing space at all — the same gate every
/// insertion site and the punctuation swap read. `wrote_romanization` is the
/// engine's verdict on the string it resolved
/// (`CommitResolution.earns_auto_space`), for a candidate and for the
/// preedit as rendered alike.
pub fn is_gate_active(is_auto_space_enabled: bool, wrote_romanization: bool) -> bool {
    is_auto_space_enabled && wrote_romanization
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
        assert!(!is_gate_active(enabled, true));
    }
}
