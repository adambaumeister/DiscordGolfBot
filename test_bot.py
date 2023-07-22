import json
from unittest.mock import MagicMock, patch
import pytest

from bot import EspnScoreboardAPI, Commands, linescores_to_rounds, get_current_round_number
from backend import GuildConfig
from search import TextItem
from test_backend import TEST_GUILD_ID, TEST_PLAYER_NAME


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


class MockSearch:
    def get_first_web_result(self, search):
        d = json.load(open("test_data/player_search_response.json"))
        return TextItem.model_validate(d)


class TestCommands:
    @patch('bot.requests')
    def test_get_top_5_events(self, mocked_requests, mocked_normal_response):
        mocked_requests.get.return_value = mocked_normal_response

        # note; no mocked backend
        commands = Commands(None)
        top5_by_event = commands.get_top_5_by_event(None)
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

    def test_get_player_profile(self, mocked_normal_response):
        commands = Commands(search_engine=MockSearch())
        player_profile_embed = commands.get_player_profile("Rory McIlroy")
        assert player_profile_embed.title == "Player Profile: Rory McIlroy"
        assert player_profile_embed.image
