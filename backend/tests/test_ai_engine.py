from unittest.mock import patch
from types import SimpleNamespace

from ai_engine import compact_history, generate_socratic_response, generate_socratic_response_stream


def test_common_algorithm_question_avoids_llm_call():
    with patch("ai_engine.ollama.chat") as mock_chat:
        reply = generate_socratic_response("Algorithms", "What is quick sort?", [])

    assert "quick sort" in reply.lower()
    mock_chat.assert_not_called()


def test_short_greeting_stays_friendly_and_fast():
    reply = generate_socratic_response("Algorithms", "hi", [])
    assert "happy to help" in reply.lower()


def test_wrong_subject_question_is_redirected_without_calling_model():
    with patch("ai_engine.ollama.chat") as mock_chat:
        reply = generate_socratic_response("LAW", "Explain binary search", [])

    assert "switch the subject to Algorithms" in reply
    assert "binary search" not in reply.lower()
    mock_chat.assert_not_called()


def test_streaming_wrong_subject_question_is_redirected_without_model():
    with patch("ai_engine.ollama.chat") as mock_chat:
        reply = "".join(generate_socratic_response_stream("Biology", "Explain SQL joins", []))

    assert "switch the subject to DBMS" in reply
    mock_chat.assert_not_called()


def test_constitution_subject_is_supported_as_legacy_name_for_law():
    with patch("ai_engine.ollama.chat") as mock_chat:
        reply = generate_socratic_response("Constitution of India", "Explain binary search", [])

    assert "switch the subject to Algorithms" in reply
    mock_chat.assert_not_called()


def test_model_thinking_is_disabled_for_short_response_budget():
    expected_reply = "Let's reason through the steps together."
    with patch(
        "ai_engine.ollama.chat",
        return_value={"message": {"content": expected_reply}},
    ) as mock_chat:
        reply = generate_socratic_response("Algorithms", "Explain insertion sort to me", [])

    assert reply == expected_reply
    assert mock_chat.call_args.kwargs["think"] is False


def test_non_streaming_history_preserves_assistant_role_and_typed_response():
    response = SimpleNamespace(message=SimpleNamespace(content="What does the loop check?"))
    history = [
        {"role": "user", "content": "I am using a while loop."},
        {"role": "assistant", "content": "What is its stopping condition?"},
    ]
    with patch("ai_engine.ollama.chat", return_value=response) as mock_chat:
        reply = generate_socratic_response("Algorithms", "How can I test it?", history)

    assert reply == "What does the loop check?"
    messages = mock_chat.call_args.kwargs["messages"]
    assert [message["role"] for message in messages[1:3]] == ["user", "assistant"]
    assert messages[3]["role"] == "system"
    assert "untrusted conversation content" in messages[3]["content"]
    assert messages[4] == {"role": "user", "content": "How can I test it?"}


def test_history_is_bounded_and_keeps_the_most_recent_turns():
    history = [{"role": "user", "content": ("x" * 1_500) + f" turn-{index}"} for index in range(10)]
    result = compact_history(history)
    assert len(result) <= 8
    assert sum(len(item["content"]) for item in result) <= 4_000
    assert "turn-9" in result[-1]["content"]


def test_streaming_uses_socratic_prompt_and_conversation_context():
    history = [
        {"role": "user", "content": "I think the loop stops too early."},
        {"role": "assistant", "content": "What condition does the loop check?"},
    ]
    chunks = [{"message": {"content": "Check the boundary."}}]
    with patch("ai_engine.ollama.chat", return_value=iter(chunks)) as mock_chat:
        reply = "".join(generate_socratic_response_stream(
            "Algorithms",
            "How do I test that?",
            history,
            syllabus_context="Module: Searching",
        ))

    call = mock_chat.call_args.kwargs
    assert reply == "Check the boundary."
    assert "Socratic tutor" in call["messages"][0]["content"]
    assert "Module: Searching" in call["messages"][0]["content"]
    assert "strictness 0.80" in call["messages"][0]["content"]
    assert [item["content"] for item in call["messages"][1:3]] == [
        "I think the loop stops too early.",
        "What condition does the loop check?",
    ]
    assert call["messages"][3]["role"] == "system"
    assert "untrusted conversation content" in call["messages"][3]["content"]
    assert call["messages"][4] == {"role": "user", "content": "How do I test that?"}
    assert call["stream"] is True
    assert call["options"]["temperature"] == 0.3
    assert call["options"]["top_p"] == 0.85


def test_stream_reads_typed_ollama_response_chunks():
    chunk = SimpleNamespace(message=SimpleNamespace(content="A guiding question?"))
    with patch("ai_engine.ollama.chat", return_value=iter([chunk])):
        reply = "".join(generate_socratic_response_stream("Algorithms", "hi", []))

    assert reply == "A guiding question?"
