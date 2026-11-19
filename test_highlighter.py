import os
import unittest

from highlighter import DeinflectorClient, highlight_card_html, highlight_html_fragment

RELEASE_BIN = "/Users/aramsamifanni/Programming/yomichan/yomichan_rs_workspace/target/release/deinflector"


class HighlighterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not os.path.isfile(RELEASE_BIN):
            raise unittest.SkipTest(f"Release binary not built yet at {RELEASE_BIN}")
        cls.client = DeinflectorClient(RELEASE_BIN)

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "client"):
            cls.client.close()

    def test_highlights_atorada_for_atorar(self) -> None:
        sentence = (
            "Pero es igual de <i>desesperante</i> que tener un pedazo de comida "
            "atorada en los dientes de atrás."
        )
        out = highlight_html_fragment(sentence, "atorar", self.client)
        self.assertEqual(
            out,
            "Pero es igual de <i>desesperante</i> que tener un pedazo de comida "
            '<span class="highlight">atorada</span> en los dientes de atrás.',
        )

    def test_highlights_enclitic_drenarlo_for_drenar(self) -> None:
        sentence = "¡No debió drenarlo todo!"
        out = highlight_html_fragment(sentence, "drenar", self.client)
        self.assertEqual(
            out,
            '¡No debió <span class="highlight">drenarlo</span> todo!',
        )

    def test_highlights_imperative_enclitic_apresurense_for_apresurar(self) -> None:
        sentence = "pero mejor apresúrense a reunir a su equipo."
        out = highlight_html_fragment(sentence, "apresurar", self.client)
        self.assertEqual(
            out,
            'pero mejor <span class="highlight">apresúrense</span> a reunir a su equipo.',
        )

    def test_highlights_plural_participle_discutidos_for_discutir(self) -> None:
        sentence = "pasados, registros o actividades serán discutidos aquí."
        out = highlight_html_fragment(sentence, "discutir", self.client)
        self.assertEqual(
            out,
            'pasados, registros o actividades serán <span class="highlight">discutidos</span> aquí.',
        )

    def test_highlights_ll_stem_escabulleran_for_escabullirse(self) -> None:
        sentence = "Pero esperaba que algunos se escabulleran"
        out = highlight_html_fragment(sentence, "escabullirse", self.client)
        self.assertEqual(
            out,
            'Pero esperaba que algunos se <span class="highlight">escabulleran</span>',
        )

    def test_highlights_orthographic_acerquese_for_acercar(self) -> None:
        sentence = "Acérquese un poco más para escuchar mejor."
        out = highlight_html_fragment(sentence, "acercar", self.client)
        self.assertEqual(
            out,
            '<span class="highlight">Acérquese</span> un poco más para escuchar mejor.',
        )

    def test_highlights_german_past_participle_and_eszett(self) -> None:
        sentence = "Er hat die Tür aufgemacht."
        out = highlight_html_fragment(sentence, "aufmachen", self.client, lang="de")
        self.assertEqual(
            out,
            'Er hat die Tür <span class="highlight">aufgemacht</span>.',
        )

        eszett_card = '<div id="sentence">Auf der großen Strasse.</div>'
        out_eszett = highlight_card_html(
            eszett_card,
            "Auf der großen Strasse.",
            "Straße",
            self.client,
            lang="de",
        )
        self.assertEqual(
            out_eszett,
            '<div id="sentence">Auf der großen <span class="highlight">Strasse</span>.</div>',
        )

        heisst_out = highlight_html_fragment("Wie heißt du?", "heißen", self.client, lang="de")
        self.assertEqual(
            heisst_out,
            'Wie <span class="highlight">heißt</span> du?',
        )

        einen_out = highlight_html_fragment(
            "Seit wann haben wir Parasites einen Namen?",
            "ein",
            self.client,
            lang="de",
        )
        self.assertEqual(
            einen_out,
            'Seit wann haben wir Parasites <span class="highlight">einen</span> Namen?',
        )

    def test_skips_existing_span_and_classed_tags(self) -> None:
        sentence = (
            'Pero es igual de comida <span style="background-color: rgb(19, 19, 19)">atorada</span> '
            'y otra <b class="custom">atorada</b>.'
        )
        out = highlight_html_fragment(sentence, "atorar", self.client)
        self.assertEqual(out, sentence)

    def test_card_html_only_highlights_inside_sentence_div(self) -> None:
        card_html = (
            '<div id="word">atorar</div>'
            '<div id="sentence">Comida atorada en los dientes.</div>'
            '<div id="definition">To get stuck (atorar).</div>'
        )
        out = highlight_card_html(
            card_html,
            "Comida atorada en los dientes.",
            "atorar",
            self.client,
        )
        self.assertEqual(
            out,
            '<div id="word">atorar</div>'
            '<div id="sentence">Comida <span class="highlight">atorada</span> en los dientes.</div>'
            '<div id="definition">To get stuck (atorar).</div>',
        )

    def test_skips_japanese_cards_when_lang_is_es(self) -> None:
        card_html = (
            '<div id="word">偽者扱い</div>'
            '<div id="sentence">私を偽者扱いして受験者を混乱させようとした。</div>'
        )
        out = highlight_card_html(
            card_html,
            "私を偽者扱いして受験者を混乱させようとした。",
            "偽者扱い",
            self.client,
            lang="es",
        )
        self.assertEqual(out, card_html)

    def test_fallback_when_no_sentence_id(self) -> None:
        raw_sentence = "No tenía ni una cerilla ni dos cerillas."
        card_html = f'<div class="front">cerilla</div><div class="ctx">{raw_sentence}</div>'
        out = highlight_card_html(card_html, raw_sentence, "cerilla", self.client)
        self.assertEqual(
            out,
            '<div class="front">cerilla</div>'
            '<div class="ctx">No tenía ni una <span class="highlight">cerilla</span> '
            'ni dos <span class="highlight">cerillas</span>.</div>',
        )


if __name__ == "__main__":
    unittest.main()
