"""The safe text format (tools/textfmt.py): what it does, and what it refuses."""
import textfmt


def test_paragraphs_and_line_breaks():
    out = str(textfmt.block("First line\nsame paragraph\n\nSecond paragraph\n\n\n\nThird"))
    assert out == "<p>First line<br>same paragraph</p>\n<p>Second paragraph</p>\n<p>Third</p>"


def test_paragraph_class():
    assert str(textfmt.block("a\n\nb", p_class="body")) == '<p class="body">a</p>\n<p class="body">b</p>'


def test_bold_and_italic():
    assert str(textfmt.inline("**bold** and *italic* and _also_")) == \
        "<strong>bold</strong> and <em>italic</em> and <em>also</em>"


def test_site_and_contact_links():
    assert str(textfmt.inline("see the [menu](/menu)")) == 'see the <a href="/menu">menu</a>'
    assert str(textfmt.inline("[form](/catering#catering)")) == '<a href="/catering#catering">form</a>'
    assert str(textfmt.inline("[top](#top)")) == '<a href="#top">top</a>'
    assert str(textfmt.inline("[mail](mailto:hi@example.com)")) == '<a href="mailto:hi@example.com">mail</a>'
    assert str(textfmt.inline("[call](tel:+15105550123)")) == '<a href="tel:+15105550123">call</a>'


def test_external_link_opens_new_tab_with_hint():
    out = str(textfmt.inline("[site](https://example.com/a?b=1&c=2)"))
    assert out == ('<a href="https://example.com/a?b=1&amp;c=2" target="_blank" rel="noopener">site'
                   '<span class="sr-only"> (opens in a new tab)</span></a>')


def test_custom_hint():
    out = str(textfmt.inline("[order](https://shop.example)", hint_for=lambda u: " (opens the shop)"))
    assert '<span class="sr-only"> (opens the shop)</span>' in out


def test_html_is_escaped_never_rendered():
    out = str(textfmt.block("<script>alert(1)</script> <b>x</b> & <img src=x onerror=alert(1)>"))
    assert "<script>" not in out and "<b>" not in out and "<img" not in out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out
    assert "&amp;" in out


def test_dangerous_urls_become_plain_text():
    for url in ("javascript:alert(1)", "JavaScript:alert(1)", "http://example.com", "//evil.example",
                "/\\evil.example", "data:text/html;base64,PHNjcmlwdD4=", "vbscript:x", "ftp://x"):
        out = str(textfmt.inline(f"[click]({url})"))
        assert "<a" not in out, url
        assert out == "click", url


def test_quote_cannot_break_out_of_href():
    out = str(textfmt.inline('[x](https://a.example/"onmouseover="alert(1))'))
    assert 'onmouseover="' not in out
    assert "&#34;" in out or "&quot;" in out


def test_unbalanced_and_inword_markers_stay_literal():
    assert str(textfmt.inline("**not closed")) == "**not closed"
    assert str(textfmt.inline("a * b * c")) == "a * b * c"
    assert str(textfmt.inline("snake_case_name and file_name.jpg")) == "snake_case_name and file_name.jpg"
    assert str(textfmt.inline("[no url]")) == "[no url]"
    assert str(textfmt.inline("[text](not a url)")) == "[text](not a url)"


def test_parentheses_in_urls():
    out = str(textfmt.inline("[acai](https://en.wikipedia.org/wiki/A%C3%A7a%C3%AD_(fruit)) bowls"))
    assert 'href="https://en.wikipedia.org/wiki/A%C3%A7a%C3%AD_(fruit)"' in out and out.endswith("</a> bowls")


def test_markers_inside_urls_are_not_emphasis():
    out = str(textfmt.inline("[a](/x_y_z) and [b](https://e.example/*q*)"))
    assert "<em>" not in out


def test_emphasis_inside_link_text():
    assert str(textfmt.inline("[**menu**](/menu)")) == '<a href="/menu"><strong>menu</strong></a>'


def test_nul_and_windows_newlines():
    assert str(textfmt.block("a\r\n\r\nb\x00")) == "<p>a</p>\n<p>b</p>"


def test_plain_counts_what_readers_see():
    assert textfmt.plain("See the **[menu](/menu)** _now_") == "See the menu now"
