## SELECT (slightly smarter) + COMPRESS + WRITE + ISOLATE
##
## This file shows the WSCI context-engineering steps:
##   SELECT   : Python picks the relevant knowledge files with keyword rules.
##   COMPRESS : Qwen extracts only the information relevant to the question.
##   WRITE    : the structured result is saved as a state.json artifact and
##              reused on later runs.
##   ISOLATE  : separate, small state artifacts are built for different tasks
##              (diagnostic vs. report); Qwen classifies the task and the
##              program only attaches the matching state to the final call.

from pathlib import Path
import json
from ollama import chat


## The local Qwen model used by Ollama (pull once with: ollama pull qwen2.5:7b)
MODEL = "qwen2.5:7b"

question = """
I changed my university password this morning.
Now my Windows laptop won't connect to campus Wi-Fi,
but my phone still works.
"""


def qwen(system_prompt, user_prompt):
    """Small helper around a single Qwen chat call."""
    response = chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.message.content


## WRITE (initial artifact) ##
# Before any reasoning we persist the facts we already know as a structured
# state artifact. Later steps read this file back instead of re-deriving them.
service_status = {
    "wifi": "operational",
    "email": "operational",
    "vpn": "operational",
    "printing": "operational",
    "learning_platform": "operational",
}

state = {
    "problem": question.strip(),
    "service_status": service_status,
    "wi_fi status": "operational",
    "wi-fi_check": True,
}

with open("state.json", "w", encoding="utf-8") as file:
    json.dump(state, file, indent=2)

with open("state.json", "r", encoding="utf-8") as file:
    state = json.load(file)

print("Initial state:", state)


## SELECT CONTEXT FILES BASED ON QUESTION
## Create the function that takes the student's question, takes some keywords and chooses the relevant files from the knowledge base. Return a list of the selected files.
## For example, if the question has the keyword "print" or "printer", then the function should return the file "knowledge/printing.txt" in a list.
KEYWORD_TO_FILES = {
    "wifi_setup.txt": [
        "wifi", "wi-fi", "eduroam", "wireless", "network", "internet",
        "connect", "connection", "laptop",
    ],
    "password_changes.txt": [
        "password", "credential", "credentials", "login", "log in",
        "authentication", "authenticate", "locked", "lockout", "changed",
    ],
    "service_status.txt": [
        "outage", "down", "status", "operational", "not working",
        "cannot connect", "can't connect", "won't connect",
    ],
    "email_setup.txt": [
        "email", "e-mail", "mail", "webmail", "inbox",
    ],
    "vpn.txt": [
        "vpn", "remote access", "outside campus",
    ],
    "printing.txt": [
        "print", "printer", "printing", "print queue",
    ],
    "classroom_projectors.txt": [
        "projector", "projectors", "display", "screen", "hdmi",
        "presentation", "monitor",
    ],
}


def select_context(question):
    """Return the knowledge-base files whose keywords appear in the question."""
    text = question.lower()
    selected = []
    for filename, keywords in KEYWORD_TO_FILES.items():
        if any(keyword in text for keyword in keywords):
            selected.append(str(Path("knowledge") / filename))
    # A Wi-Fi issue always needs the current service status so we never
    # confuse a device problem with a campus-wide outage.
    status_file = str(Path("knowledge") / "service_status.txt")
    if any("wifi" in f for f in selected) and status_file not in selected:
        selected.append(status_file)
    return selected


selected_files = select_context(question)
print("Selected files:", selected_files)

## READ SELECTED FILES and add their contents to the context variable.
context = ""

for filename in selected_files:
    context += Path(filename).read_text(encoding="utf-8")
    context += "\n\n"

print("Raw context characters:", len(context))


##
## COMPRESS CONTEXT
## Add logic to compress the context from above by calling Qwen with "context" and the "question" as the parameter
## The response from Qwen should be the compressed context. Store it in a variable called "compressed_context"

def compress_context(context, question):
    """Ask Qwen to keep only the context information that is relevant
    to the student's question."""
    system_prompt = (
        "You are a context compression engine for a university IT support "
        "system. You are given a knowledge-base context and a student's "
        "question. Rewrite the context so that it contains ONLY the facts and "
        "steps that are relevant to answering the question. Remove every "
        "unrelated topic. Keep the remaining information factual and in the "
        "same language as the context. Do not answer the question yourself."
    )
    user_prompt = (
        f"Student question:\n{question}\n\n"
        f"Knowledge-base context:\n{context}\n\n"
        "Compressed context:"
    )
    return qwen(system_prompt, user_prompt)


compressed_context = compress_context(context, question)


## Print the length of the compressed context
print("Compressed context characters:", len(compressed_context))

## Now, call Qwen again with the compressed context and the student's question. Store the response in a variable called "response" and print the response from Qwen.
## Ensure the model produces a structured output
diagnostic_system_prompt = (
    "You are a university IT support assistant. Use only the compressed "
    "context provided. Diagnose the student's problem and return STRICT JSON "
    "(no markdown, no commentary) with this schema:\n"
    '{"category": string, "device": string, "wifi_status": string, '
    '"root_cause": string, "steps": [string], "escalation": string}'
)
diagnostic_user_prompt = (
    f"Compressed context:\n{compressed_context}\n\n"
    f"Student question:{question}"
)
response = qwen(diagnostic_system_prompt, diagnostic_user_prompt)


print(response)


def parse_json(text):
    """Parse JSON from a model response, tolerating ```json fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    return json.loads(cleaned[start:end + 1])


diagnosis = parse_json(response)


## WRITE the above output in an artifact called "state"
# The diagnosis is merged into the same structured state artifact and saved.
state["classification"] = None  # filled in during ISOLATE below
state["diagnosis"] = diagnosis

# A separate reporting artifact (example support-desk statistics).
state["report"] = {
    "total_wifi_cases": 37,
    "resolved_cases": 29,
    "unresolved_cases": 8,
}

with open("state.json", "w", encoding="utf-8") as file:
    json.dump(state, file, indent=2)


## ISOLATE ##
# Different agent tasks need different slices of the state. We build small,
# isolated contexts instead of attaching the whole artifact, and we let Qwen
# classify which task this is so the program can pick the right slice.
def classify_task(question):
    """Return 'diagnostic' for a user troubleshooting request or 'report'
    for a request about statistics/reporting."""
    system_prompt = (
        "Classify the user's request as either 'diagnostic' (one user needs "
        "help troubleshooting an IT problem) or 'report' (statistics or a "
        "summary of support cases). Reply with one word only: "
        "diagnostic or report."
    )
    label = qwen(system_prompt, question).strip().lower()
    if "report" in label:
        return "report"
    return "diagnostic"


task_type = classify_task(question)
state["classification"] = task_type
with open("state.json", "w", encoding="utf-8") as file:
    json.dump(state, file, indent=2)
print("Task classified as:", task_type)


# Two isolated artifacts, each exposing only the fields its task needs.
diagnostic_context = {
    "problem": state["problem"],
    "device": diagnosis.get("device", "unknown"),
    "wifi_status": state["service_status"]["wifi"],
    "root_cause": diagnosis.get("root_cause"),
    "steps": diagnosis.get("steps", []),
    "escalation": diagnosis.get("escalation"),
}

report_context = {
    "total_wifi_cases": state["report"]["total_wifi_cases"],
    "resolved_cases": state["report"]["resolved_cases"],
    "unresolved_cases": state["report"]["unresolved_cases"],
}

# Depending on the agent's task, the appropriate isolated state is used.
isolated_context = (
    report_context if task_type == "report" else diagnostic_context
)
print("Isolated context used:", isolated_context)

final_system_prompt = {
    "diagnostic": (
        "You are a university IT support assistant. Using only the provided "
        "state, give the student a short, friendly final answer with numbered "
        "steps."
    ),
    "report": (
        "You are a university IT support analyst. Using only the provided "
        "state, write a short management report summarising the Wi-Fi case "
        "numbers."
    ),
}[task_type]

final_user_prompt = (
    f"State:\n{json.dumps(isolated_context, indent=2)}\n\n"
    f"Student question:{question}"
)
final_answer = qwen(final_system_prompt, final_user_prompt)

## Final answer produced from the isolated state artifact only.
print(final_answer)
