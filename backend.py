from typing import List, Optional
import logging
from pydantic import BaseModel, Field
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

LOGGER = logging.getLogger()


class Flag(BaseModel):
    href: str
    country: str = Field(alias="alt")


class PlayerDetails(BaseModel):
    fullName: str
    shortName: str
    flag: Flag


class GuildConfig(BaseModel):
    guild_id: int
    track_players: List[str]
    notification_channel: Optional[int] = None
    notifications_enabled: bool = False
    event_notifications: List[str] = []


class BackendStore:
    """
    Provides simple, document-based storage for Bot users.
    """

    CONFIG_COLLECTION_NAME = "guildConfigs"

    def __init__(self):
        cred = credentials.ApplicationDefault()

        try:
            firebase_admin.get_app()
        except ValueError:
            LOGGER.warning("Firebase default app being initialized.")
            firebase_admin.initialize_app(cred)

        self.db = firestore.client()

    def add_or_get_guild_config(self, guild_id: int):
        """Return the given guilds configuration"""
        guild_id = str(guild_id)
        data = self.db.collection(self.CONFIG_COLLECTION_NAME).document(guild_id).get().to_dict()
        if not data:
            LOGGER.info(f"Adding new guild config for {guild_id}.")

            guild_config = GuildConfig(
                guild_id=guild_id,
                track_players=[],
            )
            self.db.collection(self.CONFIG_COLLECTION_NAME).document(guild_id).set(dict(guild_config))
            return guild_config

        return GuildConfig(**data)

    def add_tracked_player(self, guild_id: int, player_name: str):
        """Adds the selected player to the list of tracked players."""
        # Coerce guild_id from its original integer value to a str so it can be used as a document ID
        guild_config = self.add_or_get_guild_config(guild_id)
        guild_id = str(guild_id)

        LOGGER.info(f"Updating data for {guild_id}.")
        if player_name not in guild_config.track_players:
            guild_config.track_players.append(player_name)
            self.db.collection(self.CONFIG_COLLECTION_NAME).document(guild_id).set(dict(guild_config))

        return guild_config

    def enable_notifications(self, guild_id: int, channel_id: int):
        """Enables notifications from this bot to the server in the given channel."""
        guild_config = self.add_or_get_guild_config(guild_id)
        guild_id = str(guild_id)
        LOGGER.info(f"Updating data for {guild_id}.")

        guild_config.notifications_enabled = True
        guild_config.notification_channel = channel_id
        self.db.collection(self.CONFIG_COLLECTION_NAME).document(guild_id).set(dict(guild_config))

        return guild_config

    def get_notification(self, guild_id, notification_title):
        guild_config = self.add_or_get_guild_config(guild_id)
        if notification_title in guild_config.event_notifications:
            return True

    def add_sent_notification(self, guild_id, notification_title):
        guild_config = self.add_or_get_guild_config(guild_id)
        guild_id = str(guild_id)
        if notification_title not in guild_config.event_notifications:
            LOGGER.info(f"Updating sent notification data for {guild_id}.")
            guild_config.event_notifications.append(notification_title)
            self.db.collection(self.CONFIG_COLLECTION_NAME).document(guild_id).set(dict(guild_config))

    def get_guilds_with_notifications(self):
        """Returns all the GuildConfig objects that have notifications enabled."""
        docs = (
            self.db.collection(self.CONFIG_COLLECTION_NAME)
                .where(filter=firestore.firestore.FieldFilter("notifications_enabled", "==", True))
                .stream()
        )

        guilds = []
        for doc in docs:
            guilds.append(
                GuildConfig(**doc.to_dict())
            )

        return guilds
