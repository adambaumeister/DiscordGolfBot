import json

from bot import EspnScoreboardAPI, Commands, linescores_to_rounds, get_current_round_number
from unittest.mock import MagicMock, patch
import pytest


@pytest.fixture
def mocked_normal_response():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = json.load(open("test_data/scoreboard_response.json"))

    return mock_response


class TestESPNScoreBoardAPI:
    @patch('bot.requests')
    def test_get_root_scoreboard(self, mocked_requests, mocked_normal_response):
        mocked_requests.get.return_value = mocked_normal_response

        scoreboard = EspnScoreboardAPI.get_scoreboard()
        assert len(scoreboard.events) == 2

        rounds = linescores_to_rounds(scoreboard.events[0].competitions[0].players[0].linescores)
        assert len(rounds.scorecards) == 1

        assert get_current_round_number([
            linescores_to_rounds(x.linescores) for x in scoreboard.events[0].competitions[0].players
        ]) == 2


class TestCommands:
    @patch('bot.requests')
    def test_get_root_scoreboard(self, mocked_requests, mocked_normal_response):
        mocked_requests.get.return_value = mocked_normal_response

        commands = Commands()
        top5_by_event = commands.get_top_5_by_event()
        assert len(top5_by_event[0].fields) == 5
