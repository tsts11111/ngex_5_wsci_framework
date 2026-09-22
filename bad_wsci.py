## This file is a bad way of managing context.
## It dumps EVERY knowledge-base file into the model's context,
## even though most of the files are irrelevant to the question.

from pathlib import Path
from ollama import chat


## The local Qwen model used by Ollama (pull once with: ollama pull qwen2.5:7b)
MODEL = "qwen2.5:7b"

question = """
I changed my university password this morning.
Now my Windows laptop won't connect to campus Wi-Fi,
but my phone still works.
"""


context = ""

for file in Path("knowledge").glob("*.txt"):
    context += file.read_text(encoding="utf-8")
    context += "\n\n"

## Make a call to Qwen with student's question and the context from the knowledge base.
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

## Just for fun, print the total length of the context
print(
    "Context characters:",
    len(context)
)

## Print the response from Qwen
print(response.message.content)
