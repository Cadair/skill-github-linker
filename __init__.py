import logging
from textwrap import dedent
import aiohttp

from opsdroid.connector.matrix import ConnectorMatrix
from opsdroid.connector.matrix.connector import MatrixException
from opsdroid.connector.matrix.events import GenericMatrixRoomEvent
from opsdroid.events import Message, Reply
from opsdroid.matchers import match_regex
from opsdroid.skill import Skill
from opsdroid.database.matrix import memory_in_event_room

LOG = logging.getLogger(__name__)


# This regex is taken from https://github.com/sindresorhus/issue-regex under the MIT license
REPO_REGEX = r"(?:(?<organization>[a-zA-Z\d](?:[a-zA-Z\d-]{0,37}[a-zA-Z\d])?)\/(?<repository>[\w.-]{1,100}))"
ISSUE_REGEX = r"(?<!\w)" + REPO_REGEX + r"?(?<!(?:\/\.{1,2}))#(?<issue_number>[1-9]\d{0,9})\b"


def rich_response(message, body, formatted_body):
    if isinstance(message.connector, ConnectorMatrix):
        return GenericMatrixRoomEvent(
            "m.room.message",
            {
                "body": body,
                "format": "org.matrix.custom.html",
                "formatted_body": dedent(formatted_body),
                "msgtype": "m.notice" if message.connector.send_m_notice else "m.text",
                "m.relates_to": {
                    "m.in_reply_to": {
                        "event_id": message.event_id,
                    },
                },
            },
        )
    else:
        return Reply(body, linked_event=message)


class GitHubLinks(Skill):
    github_api_url = "https://api.github.com"

    async def lookup_issue(self, organization, repository, issue_number):
        LOG.info("Looking up issue %s/%s#%s", organization, repository, issue_number)
        lookup_url = f"{self.github_api_url}/repos/{organization}/{repository}/issues/{issue_number}"
        if organization is None or repository is None or issue_number is None:
            return

        async with aiohttp.ClientSession() as session:
            async with session.get(lookup_url) as response:
                if response.status != 200:
                    LOG.error("GitHub API request failed: %s", response)
                    return
                return await response.json()

    @match_regex(ISSUE_REGEX)
    @memory_in_event_room
    async def linkify(self, message):
        default_repo = await self.opsdroid.memory.get("default_repo")
        default_org = await self.opsdroid.memory.get("default_org")
        org = message.entities['organization']['value'] or default_org
        repo = message.entities['repository']['value'] or default_repo
        issue_number = message.entities['issue_number']['value']
        if org is None or repo is None:
            reminder_sent = await self.opsdroid.memory.get("default_repo_reminder_sent")
            if not reminder_sent:
                await message.respond(Reply("No default repo is set, use `!github default_repo org/repo` to set one.",
                                            linked_event=message))
                try:
                    await self.opsdroid.memory.put("default_repo_reminder_sent", True)
                except Exception:
                    pass
            return

        issue = await self.lookup_issue(org, repo, issue_number)
        LOG.debug("Got Issue info: %s", issue)

        if issue is None:
            await message.respond(Reply(f"Couldn't lookup {org}/{repo}#{issue_number}.", linked_event=message))
            return

        labels = f" 🏷️{' '.join([l['name'] for l in issue['labels']])}" if issue['labels'] else ""
        html_labels = " ".join([f"<span data-mx-bg-color=#{l['color']}>{l['name']}</span>" for l in issue['labels']])
        html_labels = f"🏷️ {html_labels}" if issue['labels'] else ""
        milestone = f" 🪧{issue['milestone']['title']}" if issue['milestone'] is not None else ""
        milestone_html = ""
        if milestone:
            milestone_html = f"🪧{issue['milestone']['title']}"
        response = rich_response(
            message,
            f"{issue['title']} ({issue['url']}){labels}{milestone}",
            f"""\
            <a href={issue['url']}>{issue['title']}</a> #{issue['number']} {html_labels}{milestone_html}
            """,
        )
        await message.respond(response)

    @match_regex(f"!github default_repo {REPO_REGEX}")
    @memory_in_event_room
    async def set_default_repo(self, message):
        if isinstance(message.connector, ConnectorMatrix):
            power_levels = (await message.connector.connection.room_get_state_event(message.target,
                                                                                    "m.room.power_levels")).content
            admin = power_levels['events']['m.room.power_levels']
            user_pl = power_levels['users'].get(message.user_id, power_levels['users_default'])
            if user_pl < admin:
                await message.respond(f"Not authorised, you must have at least power level {admin}")
                return

        org = message.entities['organization']['value']
        repo = message.entities['repository']['value']

        try:
            await self.opsdroid.memory.put("default_org", org)
            await self.opsdroid.memory.put("default_repo", repo)
        except MatrixException as err:
            LOG.exception("Failed to store to opsdroid memory")
            await message.respond(err.nio_error.message)
            return

        await message.respond(f"Set default repo to {org}/{repo}")

