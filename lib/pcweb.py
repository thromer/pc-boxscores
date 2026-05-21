import json
from dataclasses import dataclass
from typing import cast

import requests
from google.cloud import storage


SPECS = {
    "256": {"league_name": "MLB: The Show", "recipient": "thromer (Indians)"},
    "1000": {"league_name": "thromer Sandbox", "recipient": "thromer (A0 *commish)"},
}
LOGIN_BUCKET = "pc256-creds"
LOGIN_OBJECT = "pennantchase-login.json"
LOGIN_URL = "https://www.pennantchase.com/home/login"
MESSAGE_URL_FMT = (
    "https://www.pennantchase.com/home/createmessage?email=y&passedlgid=%s"
)
USERNAME_FIELD = "txtUsername"
PASSWORD_FIELD = "txtPassword"  # noqa: S105
CHAT_URL_FMT = "https://www.pennantchase.com/socialRest/LeagueChat.aspx?lgid=%s&r=1234"
SUBMIT_CHAT_URL = "https://www.pennantchase.com/socialRest/LeagueSubmitChat.aspx"
CHAT_MESSAGE_KEY = "chatcontent"


@dataclass
class ChatEntry:
    message: str
    trailing_whitespace: int


class PcWeb:
    def __init__(self, league_id: str) -> None:
        self.league_id = league_id
        self.league_name = SPECS[league_id]["league_name"]
        self.recipient = SPECS[league_id]["recipient"]
        storage_client = storage.Client()
        login_bucket = storage.Bucket(storage_client, LOGIN_BUCKET)
        login_json = login_bucket.blob(LOGIN_OBJECT).download_as_text()
        login_map = cast(dict[str, str], json.loads(login_json))
        username = login_map["username"]
        password = login_map["password"]
        login_response = requests.post(
            LOGIN_URL,
            data={USERNAME_FIELD: username, PASSWORD_FIELD: password},
            allow_redirects=False,
            timeout=300,
        )
        login_response.raise_for_status()
        self.cookies = login_response.cookies
        # print('cookies before', self.cookies)
        _ = requests.get(
            f"https://www.pennantchase.com/lgHome.aspx?lgid={self.league_id}",
            cookies=self.cookies,
            timeout=300,
        )
        # print('cookies', self.cookies)
        self.cookies["uref"] = "https://www.pennantchase.com/home/login"
        self.cookies["lgid"] = self.league_id
        self.cookies["lgname"] = self.league_name
        self.cookies["fsbotchecked"] = "true"

    def send_to_thromer(self, subject: str, body: str) -> None:
        post_response = requests.post(
            MESSAGE_URL_FMT % self.league_id,
            cookies=self.cookies,
            data={
                "txtToName": self.recipient,
                "txtSubject": subject,
                "ddBoardCats": "6",
                "txtBody": body,
                "hidPassedLGID": self.league_id,
                "hidReplyID": "0",
                "cbEmails": "1",
                "txtToName2": "",
                "txtToName3": "",
                "txtToName4": "",
                "hidThread": "0",
                "hidEditID": "0",
            },
            timeout=300,
        )
        # print('sent url', post_response.request.url)
        # print('sent headers', post_response.request.headers)
        post_response.raise_for_status()
        if post_response.text.find("Message sent successfully") < 0:
            print("subject:", subject, "body:", body)
            raise RuntimeError(post_response.text)

    def league_chat(self, entry: ChatEntry) -> None:
        # TODO: instead of identify the the year with trailing NBSP
        # characters, instead only scan the last N days of the chat
        # when checking for the post.
        # LIMITATION: If the same event occurs in both games of a doubleheader
        # (or tripleheader, etc.), only one message will be written.
        # See if the message is already in the chat.
        # TODO: Imperfect since
        # two instances could race; consider getting a lock using the
        # game id.
        get_response = requests.get(CHAT_URL_FMT % self.league_id, timeout=300)
        get_response.raise_for_status()
        if (
            get_response.text.find(
                entry.message + "\xa0" * entry.trailing_whitespace + "<"
            )
            >= 0
        ):
            print("Already sent to chat:", entry.message)
            return
        # pretty sure these aren't needed, just cookies
        headers = {
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "user-agent": (
                "Mozilla/5.0 (X11; CrOS x86_64 13505.111.0) "
                "AppleWebKit/537.36 (khtml, like Gecko) "
                "Chrome/87.0.4280.152 Safari/537.36"
            ),
        }
        padded_message = entry.message + "%C2%A0" * entry.trailing_whitespace
        submit_response = requests.get(
            f"{SUBMIT_CHAT_URL}?clgid={self.league_id}&{CHAT_MESSAGE_KEY}={padded_message}",
            allow_redirects=False,
            cookies=self.cookies,
            headers=headers,
            timeout=300,
        )
        submit_response.raise_for_status()
        if submit_response.text.find("Chat submitted") < 0:
            print("message:", entry.message)
            raise RuntimeError(submit_response.text)
