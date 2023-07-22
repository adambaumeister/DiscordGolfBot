import os
import re
from typing import Optional, List
import requests
from pydantic import BaseModel, Field, model_validator
import datetime
from dotenv import load_dotenv
import discord
import logging

from backend import PlayerDetails, BackendStore, GuildConfig

LOGGER = logging.getLogger()
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
PLACEHOLDER_THUMBNAIL = "https://upload.wikimedia.org/wikipedia/commons/thumb/1/17/Ballybunion_Golf_Club_-_10th_hole.jpg/1024px-Ballybunion_Golf_Club_-_10th_hole.jpg"


class EventLink(BaseModel):
    ref: str = Field(alias="$ref")


class CalenderEvent(BaseModel):
    id: int
    label: str
    startDate: datetime.datetime
    endDate: datetime.datetime
    event: EventLink


class Player(BaseModel):
    id: int
    details: PlayerDetails = Field(alias="athlete")
    score: int
    linescores: List

    @model_validator(mode="before")
    def fix_int_fields(cls, data):
        score_value = data["score"]
        if type(score_value) is int:
            return data

        score_value = score_value.replace("+", "")
        score_value = score_value.replace("E", "0")
        data["score"] = int(score_value)
        return data


class Competition(BaseModel):
    id: int
    players: List[Player] = Field(alias="competitors")


class Links(BaseModel):
    href: str


class RunningEvent(BaseModel):
    id: int
    startDate: datetime.datetime = Field(alias="date")
    endDate: datetime.datetime
    name: str
    shortName: str

    competitions: List[Competition]
    links: List[Links]


class Logo(BaseModel):
    href: str
    width: int
    height: int


class League(BaseModel):
    """Golf league - aka PGA Tour"""
    id: int
    name: str
    abbreviation: str
    calendar: List[CalenderEvent]
    logos: List[Logo]


class Season(BaseModel):
    """League season"""
    year: int


class EspnScoreboardResponse(BaseModel):
    leagues: List[League]
    events: List[RunningEvent]


class EspnScoreboardAPI:
    """
    This is the low level API for the ESPN Scoreboard API. It provides basic request and response handling.

    Thank you, ESPN, for giving us this data!
    """
    ROOT_URL = "https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard"

    @staticmethod
    def get_scoreboard() -> EspnScoreboardResponse:
        response = requests.get(EspnScoreboardAPI.ROOT_URL).json()
        scoreboard = EspnScoreboardResponse.model_validate(response)
        return scoreboard


class PlayerAndScore(BaseModel):
    score: int
    player_name: str
    player_flag: str
    through: int


def text_string_compare(left, right):
    """Compare the left string to the right to see if they match."""
    if not left:
        return True

    if left.lower() == right.lower():
        return True


class Hole(BaseModel):
    number: int
    score: int


class Scorecard(BaseModel):
    holes: List[Hole]


class Rounds(BaseModel):
    scorecards: List[Scorecard]


def linescores_to_rounds(linescores: List[dict]):
    scorecards = []
    for line_score in linescores:
        value = line_score.get("value")
        if value:
            holes = []
            for number, round_linescore in enumerate(line_score.get("linescores")):
                score = round_linescore.get("value")

                holes.append(
                    Hole(
                        number=number + 1,
                        score=score
                    )
                )

            scorecards.append(
                Scorecard(
                    holes=holes
                )
            )

    return Rounds(
        scorecards=scorecards
    )


def get_current_round_number(all_rounds: List[Rounds]):
    return sorted([len(x.scorecards) for x in all_rounds], reverse=True)[0]


class Top5ResponseEmbed:
    COLOR = 0x50C878

    @staticmethod
    def get_embed(
            tournament_name: str,
            tournament_url: str,
            current_round: int,
            players_and_scores: List[PlayerAndScore]
    ):
        if not re.match("the", tournament_name.lower()):
            tournament_name = f"The {tournament_name}"

        embed = discord.Embed(
            title=f"'{tournament_name}' Leaderboard - Round {current_round}",
            url=tournament_url,
            description=f"The Top 5 players currently leading '{tournament_name}' in round number {current_round}.",
            color=Top5ResponseEmbed.COLOR
        )
        embed.set_thumbnail(url=PLACEHOLDER_THUMBNAIL)
        for player_and_score in players_and_scores:
            embed.add_field(
                name=f"🏌️‍♂️{player_and_score.player_name}",
                value=f"{player_and_score.score} through {player_and_score.through} holes.",
                inline=False
            )

        embed.set_footer(text="Some events may be omitted based on your tracked player settings.")

        return embed


class CalenderResponseEmbed:
    COLOR = 0x7FFFD4

    @staticmethod
    def get_embed(
            league_name: str,
            league_icon: str,
            running_events: List[CalenderEvent],
            upcoming_calender_events: List[CalenderEvent]
    ):
        embed = discord.Embed(
            title=f"📅 Upcoming {league_name} Golf Tournaments",
            description="The list of upcoming golf tournaments within the next 30 days.",
            color=CalenderResponseEmbed.COLOR
        )
        for calender_event in running_events:
            embed.add_field(
                name=f"{calender_event.label}",
                value="⛳ Currently in progress!",
                inline=True
            )

        embed.set_thumbnail(url=league_icon)

        for calender_event in upcoming_calender_events:
            nice_date_string = calender_event.startDate.strftime("%d/%m/%Y")
            embed.add_field(
                name=f"{calender_event.label}",
                value=f"Starts on {nice_date_string}.",
                inline=True
            )

        return embed


class Commands:

    def __init__(self, backend: Optional[BackendStore]):
        self.backend = backend

    def _get_guild_config(self, guild_id):
        if self.backend:
            return self.backend.get_guild_config(guild_id)
        else:
            return GuildConfig(
                guild_id=guild_id,
                track_players=[]
            )

    def _filter_events_by_guild_config(self, guild_id: int, events: List[RunningEvent]):
        if not guild_id:
            return events

        guild_config = self._get_guild_config(guild_id)
        track_players = [x.lower() for x in guild_config.track_players]

        filtered_events = []
        for event in events:
            competition_players = [x.details.fullName.lower() for x in event.competitions[0].players]
            if bool(set(track_players) & set(competition_players)):
                filtered_events.append(event)

        return filtered_events

    def get_current_events(self, guild_id: Optional[int] = None, event_name_filter: Optional[str] = None):
        scoreboard = EspnScoreboardAPI.get_scoreboard()
        filtered_events = self._filter_events_by_guild_config(guild_id, scoreboard.events)
        return [x for x in filtered_events if text_string_compare(event_name_filter, x.name)]

    def get_upcoming_events(self) -> List[discord.Embed]:
        scoreboard = EspnScoreboardAPI.get_scoreboard()
        future_events = []
        current_events = []
        today = datetime.datetime.today()
        today = today.replace(tzinfo=datetime.timezone.utc)
        embeds = []
        for league in scoreboard.leagues:
            for calender_event in league.calendar:
                if calender_event.endDate > today > calender_event.startDate:
                    current_events.append(calender_event)
                elif today < calender_event.startDate < today + datetime.timedelta(days=30):
                    future_events.append(calender_event)

            embeds.append(
                CalenderResponseEmbed.get_embed(
                    league_name=league.name,
                    league_icon=league.logos[-1].href,
                    running_events=current_events,
                    upcoming_calender_events=future_events
                )
            )

        return embeds

    def get_top_5_by_event(
            self,
            guild_id: Optional[int],
            event_name_filter: Optional[str] = None
    ) -> List[discord.Embed]:
        events = self.get_current_events(guild_id, event_name_filter)
        top_five_by_event = {}
        embeds = []

        for event in events:
            players = event.competitions[0].players
            current_round = get_current_round_number([
                linescores_to_rounds(x.linescores) for x in players
            ])
            player_and_scores = []
            for player in players:
                rounds = linescores_to_rounds(player.linescores)

                try:
                    through = len(rounds.scorecards[current_round - 1].holes)
                except IndexError:
                    through = 0

                player_and_scores.append(PlayerAndScore(
                    score=player.score,
                    player_name=player.details.fullName,
                    player_flag=player.details.flag.href,
                    through=through
                ))

            player_and_scores.sort(key=lambda x: x.score)
            top_five_by_event[event.name] = player_and_scores[:5]

            embeds.append(
                Top5ResponseEmbed.get_embed(
                    tournament_name=event.name,
                    tournament_url=event.links[0].href,
                    players_and_scores=player_and_scores[:5],
                    current_round=current_round
                )
            )

        return embeds

    def add_tracked_player(self, guild_id: int, player_name: str):
        """Adds a player to be 'tracked', which filters all events to only those which
        feature them. Keeps the reported scoreboards from getting too gross, though doesn't currently
        effect calander events as we can't see the roster in advance."""

        try:
            self.backend.add_tracked_player(guild_id, player_name)
            return f"Added {player_name} to the list of tracked players!"
        except Exception:
            return "Failed to add player - backend failure."


class BotClient(discord.Client):
    def __init__(self, intents: discord.Intents):
        super(BotClient, self).__init__(intents=intents)
        self.tree = discord.app_commands.CommandTree(self)

    async def on_ready(self):
        LOGGER.info(f'Logged on as {self.user}!')
        for guild in self.guilds:
            LOGGER.info(f"copying commands to {guild.name}")
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            LOGGER.info("Done - Client connected.")


backend_store = None
if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
    # Only enable the backend store if we've been given creds.
    backend_store = BackendStore()

intents = discord.Intents.default()
intents.message_content = True
client = BotClient(intents=intents)

commands = Commands(backend_store)


@client.tree.command(name="show_leaderboards", description="Show running tournament leaderboards.")
async def show_leaderboards(interaction: discord.Interaction):
    """Displays the running tournament leaderboards."""
    embeds = commands.get_top_5_by_event(guild_id=interaction.guild_id)
    await interaction.response.send_message(embeds=embeds)


@client.tree.command(name="show_upcoming_events", description="Show the upcoming and in progress golf tournaments.")
async def show_upcoming_events(interaction: discord.Interaction):
    """Displays the current and upcoming golf events, as published by ESPN."""
    embeds = commands.get_upcoming_events()
    await interaction.response.send_message(embeds=embeds)


@client.tree.command(
    name="add_tracked_player",
    description="Add a player to be tracked, which filters the events to only those that feature them.",
)
async def add_tracked_player(interaction: discord.Interaction, player_name: str):
    """Displays the current and upcoming golf events, as published by ESPN."""
    commands.add_tracked_player(interaction.guild_id, player_name)
    await interaction.response.send_message(f"{player_name} Successfully added to your tracked player list.")


if __name__ == '__main__':
    client.run(BOT_TOKEN)
