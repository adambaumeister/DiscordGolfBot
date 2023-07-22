import json

from bot import EspnScoreboardAPI, Commands, linescores_to_rounds, get_current_round_number
from backend import GuildConfig
from test_backend import TEST_GUILD_ID, TEST_PLAYER_NAME
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


class MockBackend:
    def get_guild_config(self, guild_id):
        return GuildConfig(
            guild_id=TEST_GUILD_ID,
            track_players=[TEST_PLAYER_NAME]
        )


class TestCommands:
    @patch('bot.requests')
    def test_get_root_scoreboard(self, mocked_requests, mocked_normal_response):
        mocked_requests.get.return_value = mocked_normal_response

        # note; no mocked backend
        commands = Commands(None)
        top5_by_event = commands.get_top_5_by_event()
        assert len(top5_by_event[0].fields) == 5

    @patch('bot.requests')
    def test_get_calender_events(self, mocked_requests, mocked_normal_response):
        mocked_requests.get.return_value = mocked_normal_response

        commands = Commands(None)
        embeds = commands.get_upcoming_events()

        assert len(embeds) == 1
        current_field = next(x for x in embeds[0].fields if "The Open" in x.name)
        assert current_field.value == "⛳ Currently in progress!"

        future_field = next(x for x in embeds[0].fields if "3M Open" in x.name)
        assert future_field.value == "Starts on 27/07/2023."

    @patch('bot.requests')
    def test_filtered_events(self, mocked_requests, mocked_normal_response):
        mocked_requests.get.return_value = mocked_normal_response

        commands = Commands(backend=MockBackend())
        matched_events = commands.get_current_events(TEST_GUILD_ID)
        assert len(matched_events) == 1