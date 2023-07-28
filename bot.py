import os
import re
from typing import Optional, List
import requests
from pydantic import BaseModel, Field, model_validator
import datetime
from dotenv import load_dotenv
import discord
from discord.ext import tasks
import logging

from search import Search
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


class EventStatusType(BaseModel):
    id: int
    name: str
    state: str
    completed: bool
    description: str


class EventStatus(BaseModel):
    type: EventStatusType


class RunningEvent(BaseModel):
    id: int
    startDate: datetime.datetime = Field(alias="date")
    endDate: datetime.datetime
    name: str
    shortName: str
    event_status: EventStatus = Field(alias="status")

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


class ResultRecord(BaseModel):
    winner: str
    winning_score: int
    second_place_score: int
    margin: int

    second_place_players: List[str]


def get_winner_and_margin(event: RunningEvent):
    """Given a completed event, return the winner and runners up, and the margin difference between them."""
    winner = event.competitions[0].players[0]
    second = event.competitions[0].players[1]

    winner_score = int(winner.score)
    second_score = int(second.score)

    runners_up = []
    for player in event.competitions[0].players:
        if player.score == second_score:
            runners_up.append(player.details.shortName)

    return ResultRecord(
        winner=winner.details.fullName,
        winning_score=int(winner_score),
        second_place_score=int(second_score),
        margin=(-(int(winner_score) - (int(second_score)))),
        second_place_players=runners_up
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
            players_and_scores: List[PlayerAndScore],
            search_engine: Optional[Search] = None
    ):
        if not re.match("the", tournament_name.lower()):
            tournament_name = f"The {tournament_name}"

        if current_round == 0:
            # If the round hasn't started yet, return a message..
            embed = discord.Embed(
                title=f"'{tournament_name}' is starting soon!",
                url=tournament_url,
                description=f"{tournament_name} is pending start - nobody has teed off just yet.",
                color=Top5ResponseEmbed.COLOR
            )
            if search_engine:
                result_image = search_engine.get_first_image(tournament_name)
                embed.set_thumbnail(url=result_image.image.thumbnailLink)
            else:
                embed.set_thumbnail(url=PLACEHOLDER_THUMBNAIL)

            embed.set_footer(text="Some events may be omitted based on your tracked player settings.")

            return embed

        embed = discord.Embed(
            title=f"'{tournament_name}' Leaderboard - Round {current_round}",
            url=tournament_url,
            description=f"The Top 5 players currently leading '{tournament_name}' in round number {current_round}.",
            color=Top5ResponseEmbed.COLOR
        )
        if search_engine:
            result_image = search_engine.get_first_image(tournament_name)
            embed.set_thumbnail(url=result_image.image.thumbnailLink)
        else:
            embed.set_thumbnail(url=PLACEHOLDER_THUMBNAIL)

        for player_and_score in players_and_scores:
            if player_and_score.through > 0:
                # Omit players that haven't tee'd off yet, if any.
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


class PlayerProfileEmbed:
    COLOR = 0x33FF80

    @staticmethod
    def get_embed(
            player_name: str,
            player_image: str,
            profile_snippet: str,
            link: str
    ):
        embed = discord.Embed(
            title=f"Player Profile: {player_name}",
            description=profile_snippet,
            color=PlayerProfileEmbed.COLOR,
            url=link
        )
        if player_image:
            embed.set_image(url=player_image)

        embed.set_footer(text="Player profile data is sourced from Wikipedia, via Google.")

        return embed


class WinnerEmbed:
    COLOR = 0xFFD700

    @staticmethod
    def get_embed(
            player_name: str,
            player_image: str,
            event_title: str,
            win_margin: int,
            win_snippet: str,
            link: str
    ):
        if not re.match("the", event_title.lower()):
            event_title = f"The {event_title}"

        margin_str = f"by {win_margin} strokes!"
        if win_margin == 1:
            f"by only {win_margin} stroke!"
        elif win_margin == 0:
            "in a playoff!"

        embed = discord.Embed(
            title=f"🏆 {player_name} has won {event_title} {margin_str}",
            description=win_snippet,
            color=PlayerProfileEmbed.COLOR,
            url=link
        )
        if player_image:
            embed.set_image(url=player_image)

        return embed


class Commands:

    def __init__(self, backend: Optional[BackendStore] = None, search_engine: Optional[Search] = None):
        self.backend = backend
        self.search_engine = search_engine

    def _get_guild_config(self, guild_id):
        if self.backend:
            return self.backend.add_or_get_guild_config(guild_id)
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

    def _check_embeds_need_notifications(self, guild_id, embeds: List[discord.Embed]):
        add = []
        for embed in embeds:
            if not self.backend.get_notification(guild_id, embed.title):
                add.append(embed)

        return add

    async def notifications(self, client: discord.Client):
        guilds_to_notify_configs = self.backend.get_guilds_with_notifications()
        for guild_config in guilds_to_notify_configs:
            if guild_config.guild_id == 12345:
                # Skip test guild id, if present in backend
                continue

            guild = client.get_guild(guild_config.guild_id)
            notification_channel = guild.get_channel(guild_config.notification_channel)

            winner_embeds = self.get_winners(guild_id=guild_config.guild_id)

            notifications_to_send = self._check_embeds_need_notifications(guild_id=guild_config.guild_id, embeds=winner_embeds)
            if notifications_to_send:
                await notification_channel.send(embeds=notifications_to_send)

    def get_winners(self, guild_id: Optional[int] = None):
        events = self.get_current_events(guild_id)
        embeds = []
        for event in events:
            if event.event_status.type.completed:
                event_result = get_winner_and_margin(event)
                search_result = self.search_engine.get_first_web_result(f"site:espn.com {event_result.winner} {event.name}")
                if not search_result:
                    win_snippet = ""
                    event_link = event.links[0].href
                else:
                    win_snippet = search_result.snippet
                    event_link = search_result.link

                if search_result.pagemap.metatags:
                    player_image = search_result.pagemap.metatags[0].image
                else:
                    player_image = PLACEHOLDER_THUMBNAIL

                embeds.append(
                    WinnerEmbed.get_embed(
                        player_name=event_result.winner,
                        player_image=player_image,
                        win_margin=event_result.margin,
                        event_title=event.name,
                        win_snippet=win_snippet,
                        link=event_link
                    )
                )

        return embeds

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
                    current_round=current_round,
                    search_engine=self.search_engine
                )
            )

        if not embeds:
            return [
                discord.Embed(
                    title="No Tournaments are currently running!",
                    description="There are no tournaments currently running, or they are all filterd by your tracked player settings. ",
                    color=Top5ResponseEmbed.COLOR
                )
            ]
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

    def enable_notifications(self, guild_id: int, channel_id: int):
        """Enables notifications and configures the channel to send 'em to."""
        try:
            self.backend.enable_notifications(guild_id, channel_id)
            return "Notifications enabled in this channel."
        except Exception:
            return "Failed to enable notifications - backend failure."

    def get_player_profile(self, player_name):
        """Uses google search to get information about a given player, from wikipedia."""
        if not self.search_engine:
            return discord.Embed(
                title="Google search API not enabled.",
                description="Whoops! The search API hasn't been enabled. This command isn't supported.",
                color=0xEE4B2B
            )

        result = self.search_engine.get_first_web_result(f"site:en.wikipedia.org {player_name} golf")
        if not result:
            return discord.Embed(
                title=f"{player_name} was not found.",
                description="Whoops! We don't know who that is, sorry.",
                color=0xEE4B2B
            )

        image = None
        for metatag in result.pagemap.metatags:
            if metatag.image:
                image = metatag.image

        return PlayerProfileEmbed.get_embed(
            player_name=player_name,
            player_image=image,
            link=result.link,
            profile_snippet=result.snippet
        )


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
search_engine = None
if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
    # Only enable the backend store if we've been given creds.
    backend_store = BackendStore()
if os.getenv("GOOGLE_SEARCH_KEY"):
    # Only enable the Google search functionality if we've been given a key
    search_engine = Search()

intents = discord.Intents.default()
intents.message_content = True
client = BotClient(intents=intents)

commands = Commands(backend_store, search_engine=search_engine)


@tasks.loop(minutes=5)
async def notifications():
    """Runs notifications for all guilds that have enabled them."""
    await commands.notifications(client)


@notifications.before_loop
async def before_notification_start():
    """Waits before async routines start"""
    LOGGER.info("Starting notification loop.")
    await client.wait_until_ready()


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


@client.tree.command(
    name="get_player_profile",
    description="Get the player profile - and hopefully a picture - of a given player by name.",
)
async def get_player_profile(interaction: discord.Interaction, player_name: str):
    """Uses Wikipedia to get player details, given a playe rname."""
    embeds = commands.get_player_profile(player_name)
    await interaction.response.send_message(embed=embeds)


@client.tree.command(
    name="enable_notifications",
    description="Turns on notifications about wins/losses and other news.",
)
async def enable_notifications(interaction: discord.Interaction):
    """Enables notifications within this channel."""
    msg = commands.enable_notifications(interaction.guild_id, interaction.channel_id)
    await interaction.response.send_message(msg)


async def setup_hook() -> None:
    notifications.start()


if __name__ == '__main__':
    # Start the notifications process by overriding the client.setup_hook function.
    client.setup_hook = setup_hook
    client.run(BOT_TOKEN)
