from backend.agent.nodes import _parse_llm_response


def test_final_answer_drops_echoed_action_block():
    text = (
        "Thought: done\nFinal Answer: Revenue peaked in **Dec 2023**.\n"
        'Action: final_answer\nAction Input: {"answer":"dup"}'
    )
    assert _parse_llm_response(text)["final_answer"] == "Revenue peaked in **Dec 2023**."


def test_final_answer_multiline_kept():
    text = "Thought: x\nFinal Answer: Line one\n- bullet\n- bullet two"
    assert _parse_llm_response(text)["final_answer"] == "Line one\n- bullet\n- bullet two"
