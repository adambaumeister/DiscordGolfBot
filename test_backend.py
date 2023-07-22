import os
import logging
import pytest

TEST_GUILD_ID = 12345
TEST_PLAYER_NAME = "Rory McIlroy"
TEST_PLAYER_NAME_2 = "Test Player"


@pytest.fixture()
def backend_fixture():
    from dotenv import load_dotenv
    load_dotenv()

    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        pytest.skip("This is an integration test and will not work without creds - skipping.")

    from backend import BackendStore
    return BackendStore()


def test_add_tracked_player(backend_fixture):
    from backend import LOGGER
    LOGGER.setLevel(logging.DEBUG)
    backend_fixture.add_tracked_player(TEST_GUILD_ID, TEST_PLAYER_NAME)
    backend_fixture.add_tracked_player(TEST_GUILD_ID, TEST_PLAYER_NAME_2)

    guild_config = backend_fixture.get_guild_config(TEST_GUILD_ID)

    assert guild_config.track_players == [TEST_PLAYER_NAME, TEST_PLAYER_NAME_2]
