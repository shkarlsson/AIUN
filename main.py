# %%
import autogen

from helpers.credentials import OPENAI_KEY
from config.system_messages import (
    ADMIN_SYSTEM_MESSAGE,
    MEDIATOR_SYSTEM_MESSAGE,
    REPORTER_SYSTEM_MESSAGE,
    SECRETARY_SYSTEM_MESSAGE,
    RESEARCHER_SYSTEM_MESSAGE,
    REPRESENTATIVE_SYSTEM_MESSAGE_TEMPLATE,
    INITIATION_MESSAGE,
)


MODEL_NAME = "gpt-4-1106-preview"  # "gpt-4-vision-preview"


# %%#

llm_config = {
    "cache_seed": 42,  # change the cache_seed for different trials
    "temperature": 0,
    "config_list": [
        {
            "model": MODEL_NAME,
            "api_key": OPENAI_KEY,
        },
    ],
    "timeout": 120,
}


# %%
user_proxy = autogen.UserProxyAgent(
    name="Admin",
    system_message=ADMIN_SYSTEM_MESSAGE,
    code_execution_config=False,
)

mediator = autogen.AssistantAgent(
    name="Mediator",
    system_message=MEDIATOR_SYSTEM_MESSAGE,
    llm_config=llm_config,
)

reporter = autogen.AssistantAgent(
    name="Reporter",
    system_message=REPORTER_SYSTEM_MESSAGE,
    llm_config=llm_config,
    code_execution_config={
        "work_dir": "reports",
    },
)

secretary = autogen.AssistantAgent(
    name="Secretary",
    system_message=SECRETARY_SYSTEM_MESSAGE,
    llm_config=llm_config,
    code_execution_config={
        "work_dir": "resolutions",
    },
)

researcher = autogen.AssistantAgent(
    name="Researcher",
    system_message=RESEARCHER_SYSTEM_MESSAGE,
    llm_config=llm_config,
)


def research(topic="Current political issues"):
    return f'Would have returned info on "{topic}", but the function is not yet implemented...'


researcher.register_function(
    function_map={
        "research": research,  # autogen seems to lack functionality for specifying arguments so hopefully the topic argument is considered implicit.
    }
)

from helpers.paths import EXPORT_DIR, REPORTS_DIR, RESOLUTIONS_DIR
from datetime import datetime


def write_to_file(text, doc_type):
    dt_str = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    filename = f"{dt_str}.md"
    if doc_type == "report":
        path = REPORTS_DIR / filename
    elif doc_type == "resolution":
        path = RESOLUTIONS_DIR / filename
    else:
        path = EXPORT_DIR / filename
        logging.warning(f"Unknown doc_type {doc_type}. Writing to {path}")
    with open(path, "w") as f:
        f.write(text)


def write_resolution(text):
    write_to_file(text, "resolution")
    return f"Resolution written to file"


def write_report(text):
    write_to_file(text, "report")
    return f"Report written to file"


secretary.register_function(
    function_map={
        "write_resolution": write_resolution,
    }
)

reporter.register_function(
    function_map={
        "write_report": write_report,
    }
)

reps = []
for country in ["Russia", "China", "USA"]:
    reps.append(
        autogen.AssistantAgent(
            name=f"{country}Rep",
            llm_config=llm_config,
            system_message=REPRESENTATIVE_SYSTEM_MESSAGE_TEMPLATE.replace(
                "COUNTRY", country
            ),
        )
    )

groupchat = autogen.GroupChat(
    agents=[user_proxy, mediator, reporter, secretary, researcher, *reps],
    messages=[],
    max_round=50,
)
# %%

manager = autogen.GroupChatManager(groupchat=groupchat, llm_config=llm_config)


user_proxy.initiate_chat(
    manager,
    message=INITIATION_MESSAGE,
)

# %%
