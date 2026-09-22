## SELECT (manual way):
## Instead of giving Qwen every file in the knowledge base,
## we hand-pick only the files that are relevant to the question
## (Wi-Fi + password change + service status) and ignore the rest.

from pathlib import Path
from ollama import chat


## The local Qwen model used by Ollama (pull once with: ollama pull qwen2.5:7b)
MODEL = "qwen2.5:7b"

question = """
I changed my university password this morning.
Now my Windows laptop won't connect to campus Wi-Fi,
but my phone still works.
"""

selected_files = [
    ##Use only the files that are relevant to the question.
    "knowledge/wifi_setup.txt",        # eduroam setup + the Windows "Forget" / reconnect fix
    "knowledge/password_changes.txt",  # cached old credentials after a password change
    "knowledge/service_status.txt",    # confirms there is no campus-wide Wi-Fi outage
]


context = ""

## Write a for loop to go through all the files in selected_files and read their contents into the context variable.
for filename in selected_files:
    context += Path(filename).read_text(encoding="utf-8")
    context += "\n\n"

## Call Qwen with the student's question and the context you created above.
response = chat(
    model=MODEL,
    messages=[
        {
            "role": "system",
            "content": (
                "You are a university IT support assistant. "
                "Diagnose the student's problem and give clear, step-by-step "
                "instructions using only the provided knowledge-base context."
            ),
        },
        {
            "role": "user",
            "content": f"Knowledge base context:\n{context}\n\n"
                       f"Student question:{question}",
        },
    ],
)


print(
    "Context characters:",
    len(context)
)
print(response.message.content)
