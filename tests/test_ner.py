from ner.recognize import extract_entities


def test_extracts_rule_based_legal_entities():
    text = "The Income-tax Act, 1961 applies under section 90 on 12 March 2024 for INR 2,000."
    entities = extract_entities(text)
    labels = {entity["label"] for entity in entities}

    assert "ACT_NAME" in labels
    assert "SECTION_REF" in labels
    assert "DATE" in labels
    assert "MONEY" in labels
