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


@pytest.fixture
def mocked_finish_response():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = json.load(open("test_data/scoreboard_finished_response.json"))

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

        assert not scoreboard.events[0].event_status.type.completed

    @patch('bot.requests')
    def test_get_root_scoreboard_event_finished(self, mocked_requests, mocked_finish_response):
        mocked_requests.get.return_value = mocked_finish_response

        scoreboard = EspnScoreboardAPI.get_scoreboard()

        assert scoreboard.events[0].event_status.type.completed


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

        # Couldn't figure out mockign datetime.today(), need to revisit this.
        assert embeds

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

    @patch('bot.requests')
    def test_get_winner(self, mocked_requests, mocked_finish_response, search_fixture):
        mocked_requests.get.return_value = mocked_finish_response

        commands = Commands(backend=MockBackend(), search_engine=search_fixture)
        embeds = commands.get_winners(TEST_GUILD_ID)
        assert embeds[0].title == "🏆 Brian Harman has won The Open by 6 strokes!"
