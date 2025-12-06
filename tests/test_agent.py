import pytest
from unittest.mock import MagicMock, AsyncMock
from pydantic_ai.models.test import TestModel
from pydantic import BaseModel
from pydantic_ai.messages import ModelResponse, ToolCallPart, TextPart, ModelRequest, ToolReturnPart
import sys

# ==========================================
# Mocking Dependencies for Imports
# ==========================================
# Use the sys.modules technique to Mock out the import of these modules.
# Ensure that test_agent.py can run independently without reporting errors.
# If you are running in a real environment, you can keep or delete this part as needed.
# ==========================================

# 1. Mock Schemas
mock_schemas_deps = MagicMock()
class MockDeps:
    def __init__(self, tavily, alpaca, allow_trading=True):
        self.tavily = tavily
        self.alpaca = alpaca
        self.allow_trading = allow_trading

mock_schemas_deps.Deps = MockDeps
sys.modules["schemas.deps"] = mock_schemas_deps

mock_schemas_output = MagicMock()
class AgentResult(BaseModel):
    message: str
mock_schemas_output.AgentResult = AgentResult
sys.modules["schemas.output"] = mock_schemas_output

# 2. Mock Integrations
sys.modules["integrations"] = MagicMock()
sys.modules["integrations.alpaca"] = MagicMock()
sys.modules["integrations.tavily"] = MagicMock()
sys.modules["integrations.alpaca.account"] = MagicMock()
sys.modules["integrations.alpaca.assets"] = MagicMock()
sys.modules["integrations.alpaca.orders"] = MagicMock()
sys.modules["integrations.alpaca.positions"] = MagicMock()
sys.modules["integrations.tavily.search"] = MagicMock()

# ==========================================
# Import System Under Test (SUT)
# ==========================================
# 3. Mock AnthropicModel to avoid API key check
class MockAnthropicModel(TestModel):
    def __init__(self, model_name, **kwargs):
        super().__init__(**kwargs)

mock_anthropic_module = MagicMock()
mock_anthropic_module.AnthropicModel = MockAnthropicModel
sys.modules["pydantic_ai.models.anthropic"] = mock_anthropic_module

# ==========================================
# Import System Under Test (SUT)
# ==========================================
from agent import agent

# ==========================================
# Test Suite
# ==========================================

@pytest.fixture
def mock_deps(mocker):
    """Create dependent Mock objects"""
    mock_tavily_client = mocker.Mock(name="tavily_client")
    mock_alpaca_client = mocker.Mock(name="alpaca_client")
    
    # Default allow trading
    return MockDeps(
        tavily=mock_tavily_client,
        alpaca=mock_alpaca_client,
        allow_trading=True
    )

def test_web_search_tool_happy_path(mocker, mock_deps):
    """
    Happy Path: Test web_search tool can correctly call the underlying tavily_web_search
    """
    # 1. Setup: Mock tavily
    mock_tavily_search = mocker.patch("agent.tavily_web_search")
    mock_tavily_search.return_value = {"results": ["news1", "news2"]}

    # 2. Setup: Mock model request to return specific tool call
    agent.model = TestModel()
    agent.model.request = AsyncMock()
    agent.model.request.side_effect = [
        ModelResponse(parts=[ToolCallPart(tool_name='web_search', args={'query': "What is the latest crypto news?", 'topic': 'news', 'days': 7})]),
        ModelResponse(parts=[TextPart('{"message": "Done"}')])
    ]

    # 3. Action
    result = agent.run_sync("What is the latest crypto news?", deps=mock_deps)

    # 4. Assertions
    # Verify tavily function is called
    mock_tavily_search.assert_called_once()
    
    # Verify parameters are passed correctly (check default parameters days=7, topic='news')
    call_args = mock_tavily_search.call_args
    assert call_args.kwargs['query'] == "What is the latest crypto news?"
    assert call_args.kwargs['days'] == 7
    assert call_args.kwargs['topic'] == "news"

def test_get_account_formatting(mocker, mock_deps):
    """
    Happy Path: Test get_account correctly handles Pydantic model serialization
    """
    # 1. Setup
    mock_get_account = mocker.patch("agent.alpaca_get_account")
    
    # Mock Alpaca return object, must contain model_dump method
    mock_account_obj = mocker.Mock()
    expected_dict = {"id": "123", "cash": "1000.00"}
    mock_account_obj.model_dump.return_value = expected_dict
    mock_get_account.return_value = mock_account_obj

    agent.model = TestModel(call_tools=["get_account"])

    # 2. Action
    # Run agent and capture tool call results.
    agent.run_sync("Check my account", deps=mock_deps)

    # 3. Assertions
    mock_get_account.assert_called_once_with(mock_deps.alpaca)
    mock_account_obj.model_dump.assert_called_once()

def test_create_order_happy_path(mocker, mock_deps):
    """
    Happy Path: When allow_trading=True, should make real order call
    """
    # 1. Setup
    mock_create_order = mocker.patch("agent.alpaca_create_order")
    mock_create_order.return_value = {"id": "order_123", "status": "filled"}
    
    mock_deps.allow_trading = True
    
    agent.model = TestModel()
    
    # 2. Action
    mock_response = ModelResponse(
        parts=[ToolCallPart(tool_name='create_order', args={'symbol': 'BTC/USD', 'notional': 100, 'side': 'buy'})]
    )
    # Use TestModel instance but mock the request method
    agent.model = TestModel()
    agent.model.request = AsyncMock()
    agent.model.request.return_value = mock_response

    agent.model.request.side_effect = [
        mock_response,
        ModelResponse(parts=[TextPart('{"message": "Done"}')])
    ]

    result = agent.run_sync("Buy $100 BTC", deps=mock_deps)

    # 3. Assertions
    mock_create_order.assert_called_once()
    assert mock_create_order.call_args.kwargs['symbol'] == "BTC/USD"
    assert mock_create_order.call_args.kwargs['notional'] == 100
    assert mock_create_order.call_args.kwargs['side'] == "buy"

def test_create_order_trading_disabled(mocker, mock_deps):
    """
    Edge Case: When allow_trading=False, should not make order call and return error
    """
    # 1. Setup
    mock_create_order = mocker.patch("agent.alpaca_create_order")
    mock_deps.allow_trading = False

    mock_response = ModelResponse(
        parts=[ToolCallPart(tool_name='create_order', args={'symbol': 'ETH/USD', 'notional': 50, 'side': 'sell'})]
    )
    agent.model = TestModel()
    agent.model.request = AsyncMock()
    agent.model.request.side_effect = [mock_response, ModelResponse(parts=[TextPart('{"message": "Done"}')])]

    # 2. Action
    agent.run_sync("Sell ETH", deps=mock_deps)

    # 3. Assertions
    mock_create_order.assert_not_called()
    
    second_call_args = agent.model.request.call_args_list[1]
    messages = second_call_args[0][0]
    
    last_msg = messages[-1]
    assert isinstance(last_msg, ModelRequest)
    
    tool_return = next(p for p in last_msg.parts if isinstance(p, ToolReturnPart))
    assert tool_return.content['ok'] is False
    assert "Trading disabled" in tool_return.content['reason']

def test_upstream_api_failure_handling(mocker, mock_deps):
    """
    Edge Case: When upstream API fails, should handle it gracefully
    """
    # 1. Setup
    mock_list_positions = mocker.patch("agent.alpaca_list_positions")
    mock_list_positions.side_effect = RuntimeError("Alpaca API Down")

    agent.model = TestModel(call_tools=["get_positions"])

    # 2. Action & Assertion    
    with pytest.raises(RuntimeError, match="Alpaca API Down"):
        agent.run_sync("Show my positions", deps=mock_deps)

def test_close_position_logic(mocker, mock_deps):
    """
    Happy Path: Test close_position tool call with correct parameters
    """
    mock_close = mocker.patch("agent.alpaca_close_position")
    mock_close.return_value.model_dump.return_value = {"status": "closed"}
    
    agent.model = TestModel()
    agent.model.request = AsyncMock()
    agent.model.request.side_effect = [
        ModelResponse(parts=[
            ToolCallPart(tool_name='close_position', args={'symbol_or_asset_id': 'BTC', 'percentage': 0.5})
        ]),
        ModelResponse(parts=[TextPart('{"message": "Done"}')])
    ]

    agent.run_sync("Close half my BTC", deps=mock_deps)

    mock_close.assert_called_once()
    assert mock_close.call_args.kwargs['symbol_or_asset_id'] == 'BTC'
    assert mock_close.call_args.kwargs['percentage'] == 0.5

if __name__ == "__main__":
    pytest.main(["-v", "-s", "test_agent.py"])