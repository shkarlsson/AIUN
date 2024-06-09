# %%
import random
import logging
from datetime import datetime
import json
from dotenv import load_dotenv

import openai
import tiktoken

from helpers.paths import DATA_DIR
from helpers.generic import INSTANCE_NO, camelize
from config.system_messages import *
from config.instance_setup import (
    MODEL_NAME,
    CONTEXT_LIMITS,
    RESPONSE_LIMIT,
)

load_dotenv()

# TODO: Add skills such as
# - reconvene(agent_to_reconvene_with [existing or to be instantiated])
# - ask(agent_to_ask_a_question_to [to cut the round robin order])
# - ask(agent_to_ask_a_question_to

logging.basicConfig(level=logging.INFO)


def log(message):
    logging.info(message)


def get_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


MEMORIES_DIR = DATA_DIR / f"instance_{INSTANCE_NO}" / "memories"
MEMORIES_DIR.mkdir(parents=True, exist_ok=True)
CHATS_DIR = DATA_DIR / f"instance_{INSTANCE_NO}" / "chats"
CHATS_DIR.mkdir(parents=True, exist_ok=True)
CHOREOGRAPHY_DIR = DATA_DIR / f"instance_{INSTANCE_NO}" / "choreography"
CHOREOGRAPHY_DIR.mkdir(parents=True, exist_ok=True)


def get_token_count(s, encoding_name="cl100k_base"):
    if isinstance(s, dict):
        s = s["content"]
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(s))
    return num_tokens


# %%


def make_chat_path(name):
    # TODO: Add ability to save consecutive chats with the same agents

    return CHATS_DIR / f"{name}.json"


class Agent:
    def __init__(self, name, system_message):
        self.name = name
        self.camel_name = camelize(name)
        self.system_message = (
            system_message
            + f'\nStart your messages with "{self.name}: " and end them with "END {self.name}".'
        )
        self.memory_path = MEMORIES_DIR / f"{name}.json"
        self.response_limit = RESPONSE_LIMIT
        self.sent_to_model = []
        self.received_from_model = []

    def __repr__(self):
        return f"Agent({self.name})"

    def get_list_of_chats(self):
        """Returns a list of chats (from a json file) as a list of dicts."""
        if not self.memory_path.exists():
            return []
        with open(self.memory_path, "r") as f:
            return json.load(f)

    def get_chat_contents(self, chat_name):
        """
        Returns the contents of a chat (from a json file) as a list of messages.

        This is part of the Agent class, not the Chat class, because the agent needs to regularly access contents from chats that might be from previous sessions, or otherwise not currently instantiated.
        chat_path = make_chat_path(chat_name)
        """
        chat_path = make_chat_path(chat_name)
        if not chat_path.exists():
            return []
        with open(chat_path, "r") as f:
            return json.load(f)

    def condense_memory(self, messages):
        """Condenses the memory to a maximum number of tokens."""
        # TODO: Use summaries of old conversations instead of cutting them off
        limited_messages = []
        tokens_left = (
            CONTEXT_LIMITS[MODEL_NAME]
            - self.response_limit
            - get_token_count(messages[0])
        )  # Starting off with space left for the system message
        for message in messages[::-1]:
            tokens = get_token_count(message)
            if tokens_left - tokens > 0:
                limited_messages.append(message)
                tokens_left -= tokens
            else:
                log(
                    f"Condensed memory from {len(messages)} to {len(limited_messages)+1} messages."
                )
                break

        limited_messages.append(messages[0])
        return limited_messages[::-1]

    def get_memory(self, for_ai=True):
        messages = [{"role": "system", "content": self.system_message}]

        chat_memory = self.get_list_of_chats()

        for chat in chat_memory:
            participants = ", ".join(chat["participants"])
            messages.append(
                {
                    "role": "system",
                    "content": f"You are in a conversation between {participants}.",
                }
            )

            chat_contents = self.get_chat_contents(chat["chat_name"])

            # Only retaining the last message from each agent
            messages += [
                {"role": x["role"], "content": x["content"]} for x in chat_contents
            ]

        return self.condense_memory(messages)

    def send_choreography_data(self, data):
        agent_choreography_path = CHOREOGRAPHY_DIR / f"{self.camel_name}.json"
        if agent_choreography_path.exists():
            choreography = json.load(open(agent_choreography_path, "r"))
        else:
            choreography = []
        choreography.append(data)
        json.dump(choreography, open(agent_choreography_path, "w"), indent=4)

    def add_chat_to_memory(self, chat_name, chat_participants):
        timestamp = get_timestamp()
        memory = self.get_list_of_chats()
        data = {
            "chat_name": chat_name,
            "participants": [x.name for x in chat_participants],
            "timestamp": timestamp,
        }
        memory.append(data)
        with open(self.memory_path, "w") as f:
            json.dump(memory, f, indent=4)

        self.send_choreography_data({"go": chat_name, "timestamp": timestamp})

    def solocit_response(self, chat_name):
        log(f"Solociting response from {self.name}")
        messages = self.get_memory()

        client = openai.OpenAI()

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            max_tokens=self.response_limit,
        )
        response_content = response.choices[0].message.content

        self.sent_to_model.append(messages)
        self.received_from_model.append(response_content)

        self.send_choreography_data(
            {"say": response_content, "timestamp": get_timestamp()}
        )

        log(f"\n{self.name}:\n{response_content}\n")
        return response_content


class Chat:
    def __init__(self, name, participants, chat_limit):
        self.name = name
        self.participants = participants
        self.path = make_chat_path(name)
        self.next_in_turn = 0
        self.chat_limit = chat_limit
        self.messages_in_chat = 0

    def __repr__(self):
        return f"Chat({self.name})"

    def add_chat_to_memories(self):
        for agent in self.participants:
            agent.add_chat_to_memory(self.name, self.participants)

    def get_chat_history(self):
        if not self.path.exists():
            self.add_chat_to_memories()
            return []
        return json.load(open(self.path, "r"))

    def add_message_to_chat(self, message, origin):
        if isinstance(origin, Agent):
            origin = origin.name
        if origin == "Admin":
            role = "system"
        else:
            role = "assistant"
        message = {
            "role": role,
            "content": message,
            "timestamp": get_timestamp(),
        }
        messages = self.get_chat_history()
        messages.append(message)
        with open(self.path, "w") as f:
            json.dump(messages, f, indent=4)
        log(f"Added message to chat {self.name}: {message}")
        self.messages_in_chat = len(messages)

    def decide_next_in_turn(self, message):
        # TODO: Let the agents assign, if they want, who shall respond next.
        return (self.next_in_turn + 1) % len(self.participants)

    def step(self, message, origin="Admin"):
        self.add_message_to_chat(message, origin)
        if self.messages_in_chat >= self.chat_limit:
            log(
                f"Chat {self.name} has reached its limit ({self.chat_limit}) and is now closed,"
            )
            return
        agent = self.participants[self.next_in_turn]

        response = agent.solocit_response(self.name)

        self.next_in_turn = self.decide_next_in_turn(response)

        self.step(response, agent.name)


countries = ["United States", "China", "Russia", "France", "United Kingdom", "Hamas"]

reps = [
    Agent(
        country + " Representative",
        REPRESENTATIVE_SYSTEM_MESSAGE_TEMPLATE.replace(
            "COUNTRY",
            country,
        ),
    )
    for country in countries
]

president = Agent("President", PRESIDENT_SYSTEM_MESSAGE)
reporter = Agent("Reporter", REPORTER_SYSTEM_MESSAGE)
# secretary = Agent("Secretary", SECRETARY_SYSTEM_MESSAGE)

chat = Chat(
    "security_council",
    [president] + reps + [reporter],
    chat_limit=40,
)
# %%
chat.step("""Discuss a current political issue (Palestine and Israel)""")

# %%
chat.step("""Discuss a current political issue (Sudan and South Sudan)""")
# %%
# Message to be sent by admin to initiate the chat
chat.step(
    """Discuss a current political issue (Sudan and South Sudan) and produce from that a resolution that increases peace in the world and is accepted by all representatives. If no resolution is accepted by all representatives, the assembly is considered a failure and you die."""
)
# %%

subset = random.sample(reps, 2)
chat2 = Chat("water_cooler", subset, chat_limit=15)
# %%
subset_str = " and ".join([x.name for x in subset])

# TODO: Make smarter conversation starter system messages that target each agent individually
chat2.step(
    f"You are standing by the watercooler in the UN halls, having an informal discussion (among {subset_str}) about whatever comes to mind."
)
# %%
subset = [reporter, president]
chat3 = Chat("water_cooler2", subset, chat_limit=15)
subset_str = " and ".join([x.name for x in subset])
chat3.step(
    f"You are standing by the watercooler in the UN halls, ventilating the previous discussion (among {subset_str})."
)

# %%
