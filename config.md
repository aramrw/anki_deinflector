# Deinflector Sentence Highlighter

Runtime highlighter that matches inflected words in your sentence field against `wordDictionaryForm` using the Rust `deinflector` binary and wraps them in a CSS class (default `.highlight`).

- **enabled**: Enable or disable runtime highlighting.
- **language**: Default language ISO code passed to `deinflector` (e.g. `"es"` or `"de"`).
- **deck_languages**: Optional map of deck name prefix to language ISO code (e.g. `{"German": "de", "Spanish": "es"}`) so multiple languages work simultaneously.
- **word_field**: Note field containing the dictionary form (default `"wordDictionaryForm"`).
- **sentence_field**: Note field containing the example sentence (default `"sentence"`).
- **sentence_element_id**: Optional HTML element `id` on the card template wrapping the sentence (default `"sentence"`). If found, only that element's contents are highlighted.
- **highlight_class**: CSS class applied to matched words (`<span class="...">`).
- **deck_prefixes**: Optional list of deck name prefixes to restrict highlighting (empty `[]` applies to all decks with matching fields).
- **binary_path**: Path to the compiled `deinflector` CLI binary.
