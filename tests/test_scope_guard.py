import os
import shutil
import pytest
from unittest.mock import MagicMock, patch
from softwiki.config import get_workspace_dir
from softwiki.intelligence.scope_guard import check_scope, get_scope_file_path

@pytest.fixture(autouse=True)
def setup_teardown_workspace():
    # Setup test workspace dir env
    orig_ws = os.environ.get("WORKSPACE_DIR")
    test_ws = os.path.abspath("data/test_scope_ws")
    os.environ["WORKSPACE_DIR"] = test_ws
    os.makedirs(test_ws, exist_ok=True)
    
    yield test_ws
    
    # Teardown
    if os.path.exists(test_ws):
        try:
            shutil.rmtree(test_ws)
        except Exception:
            pass
    if orig_ws:
        os.environ["WORKSPACE_DIR"] = orig_ws
    else:
        os.environ.pop("WORKSPACE_DIR", None)

def test_scope_guard_no_file(setup_teardown_workspace):
    # If no scope.md is present, everything is in-scope
    is_in_scope, reason = check_scope("some text", item_type="document")
    assert is_in_scope is True
    assert "No scope.md defined" in reason

@patch("softwiki.intelligence.scope_guard.get_llm_client_and_params")
def test_scope_guard_with_scope_file(mock_get_llm, setup_teardown_workspace):
    # Create scope.md
    scope_path = os.path.join(setup_teardown_workspace, "scope.md")
    with open(scope_path, "w", encoding="utf-8") as f:
        f.write("In Scope: De-dollarization\nOut of Scope: Cooking")
        
    # Mock LLM response for IN_SCOPE
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "IN_SCOPE: This is about de-dollarization"
    mock_client.chat.completions.create.return_value = mock_response
    mock_get_llm.return_value = (mock_client, "gpt-4o-mini", 0.0, None)
    
    is_in_scope, reason = check_scope("De-dollarization is rising", item_type="document")
    assert is_in_scope is True
    assert "This is about de-dollarization" in reason
    
    # Mock LLM response for OUT_OF_SCOPE
    mock_response.choices[0].message.content = "OUT_OF_SCOPE: This is about cooking, not de-dollarization"
    is_in_scope, reason = check_scope("How to bake a cake", item_type="document")
    assert is_in_scope is False
    assert "This is about cooking" in reason

@patch("softwiki.intelligence.scope_guard.get_llm_client_and_params")
def test_answer_engine_scope_enforcement(mock_get_llm, setup_teardown_workspace):
    # Create scope.md
    scope_path = os.path.join(setup_teardown_workspace, "scope.md")
    with open(scope_path, "w", encoding="utf-8") as f:
        f.write("In Scope: De-dollarization\nOut of Scope: Cooking")

    # Mock LLM response for OUT_OF_SCOPE
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "OUT_OF_SCOPE: Cooking is out of scope"
    mock_client.chat.completions.create.return_value = mock_response
    mock_get_llm.return_value = (mock_client, "gpt-4o-mini", 0.0, None)

    from softwiki.intelligence.answer_engine import AnswerEngine
    from unittest.mock import MagicMock as SqlMagicMock
    db_mock = SqlMagicMock()
    
    engine = AnswerEngine()
    answer = engine.ask(db_mock, "How to cook pasta?")
    assert "Reject" in answer
    assert "out of scope" in answer.lower()

@patch("softwiki.intelligence.scope_guard.get_llm_client_and_params")
def test_wiki_generation_scope_enforcement(mock_get_llm, setup_teardown_workspace):
    # Create scope.md
    scope_path = os.path.join(setup_teardown_workspace, "scope.md")
    with open(scope_path, "w", encoding="utf-8") as f:
        f.write("In Scope: De-dollarization\nOut of Scope: Cooking")

    # Mock LLM response for OUT_OF_SCOPE
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "OUT_OF_SCOPE: Cooking is out of scope"
    mock_client.chat.completions.create.return_value = mock_response
    mock_get_llm.return_value = (mock_client, "gpt-4o-mini", 0.0, None)

    from softwiki.wiki.page_generator import WikiPageGenerator
    from unittest.mock import MagicMock as SqlMagicMock
    db_mock = SqlMagicMock()
    
    generator = WikiPageGenerator()
    with pytest.raises(ValueError) as excinfo:
        generator.generate_topic_page(db_mock, "cooking-pasta")
    assert "Reject: The topic" in str(excinfo.value)
    assert "out of scope" in str(excinfo.value).lower()
