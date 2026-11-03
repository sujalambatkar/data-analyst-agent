from backend.agent.nodes import _decline_message, _is_off_topic, _parse_llm_response


def test_marker_variants_detected():
    for a in ["[OFF_TOPIC]", "OFF_TOPIC", "**[OFF_TOPIC]**", "[off-topic] sorry", " [OFF TOPIC]"]:
        assert _is_off_topic(a), a


def test_real_answers_not_flagged():
    assert not _is_off_topic("Revenue was $5. This is not off topic.")
    assert not _is_off_topic("")


def test_marker_parsed_from_model_output():
    text = "Thought: This is not about the data.\nFinal Answer: [OFF_TOPIC]"
    assert _is_off_topic(_parse_llm_response(text)["final_answer"])


def test_decline_lists_tables():
    msg = _decline_message("products: id(INTEGER)\nsales: id(INTEGER), revenue(DOUBLE PRECI)")
    assert "products, sales" in msg and "only help with questions about your data" in msg


def test_decline_without_schema():
    assert "Right now" not in _decline_message("")
