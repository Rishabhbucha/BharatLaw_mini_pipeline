from chunker.chunk import _semantic_blocks


def test_semantic_blocks_track_heading_path_and_page_number():
    text = "# Title\n\n## Page 3\n\n### Section A\n\nA paragraph about legal material."
    blocks = _semantic_blocks(text)

    assert blocks[-1]["section_path"] == ["Title", "Page 3", "Section A"]
    assert blocks[-1]["page_no"] == 3
